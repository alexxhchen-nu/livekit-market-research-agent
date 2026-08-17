import {
  Room,
  RoomEvent,
  Track,
} from "https://cdn.jsdelivr.net/npm/livekit-client@2.21.0/+esm";

const setupView = document.querySelector("#setup-view");
const liveView = document.querySelector("#live-interview");
const startButton = document.querySelector("#start");
const endButton = document.querySelector("#end");
const newInterviewButton = document.querySelector("#new-interview");
const recordButton = document.querySelector("#record");
const copyButton = document.querySelector("#copy-id");
const status = document.querySelector("#connection-status");
const dot = document.querySelector("#connection-dot");
const setupMessage = document.querySelector("#setup-message");
const liveMessage = document.querySelector("#live-message");
const interviewId = document.querySelector("#interview-id");
const resumeId = document.querySelector("#resume-id");
const downloadJson = document.querySelector("#download-json");
const downloadCsv = document.querySelector("#download-csv");
const turnIcon = document.querySelector("#turn-icon");
const turnStatus = document.querySelector("#turn-status");
const turnDetail = document.querySelector("#turn-detail");
const transcript = document.querySelector("#transcript");
const transcriptEmpty = document.querySelector("#transcript-empty");
const transcriptCount = document.querySelector("#transcript-count");
const recordingNotice = document.querySelector("#recording-notice");

const studyFields = {
  topic: "#study-topic",
  client_context: "#study-client",
  target_audience: "#study-audience",
  objective: "#study-objective",
  questions: "#study-questions",
};

let room;
let currentInterviewId;
let currentDownloadToken;
let agentParticipant;
let micEnabled = false;
let recordingActive = false;
const transcriptItems = new Map();

function setStatus(text, connected = false) {
  status.textContent = text;
  dot.classList.toggle("connected", connected);
}

function showSetupMessage(text) {
  setupMessage.textContent = text;
}

function showLiveMessage(text) {
  liveMessage.textContent = text;
}

function setTurn(state, detail) {
  const labels = {
    speaking: ["Interviewer is speaking", "Listen to the question.", "voice"],
    thinking: ["Interviewer is thinking", "Press Record answer when you're ready to respond.", "thinking"],
    listening: ["Recording your answer", "Press Stop & send when you are finished.", "mic"],
  };
  const [label, copy, icon] = labels[state] || labels.thinking;
  turnStatus.textContent = label;
  turnDetail.textContent = detail || copy;
  turnIcon.textContent = icon === "mic" ? "◉" : icon === "thinking" ? "…" : "◌";
  document.body.dataset.turn = state;
}

function setDownloadState() {
  const ready = Boolean(currentInterviewId && currentDownloadToken);
  downloadJson.disabled = !ready;
  downloadCsv.disabled = !ready;
}

function resumeToken() {
  const id = resumeId.value.trim();
  return id ? localStorage.getItem(`research-resume-token:${id}`) : null;
}

function collectStudy() {
  const study = {};
  for (const [key, selector] of Object.entries(studyFields)) {
    const value = document.querySelector(selector).value.trim();
    if (value) study[key] = value;
  }
  return study;
}

async function requestSession() {
  const response = await fetch("/api/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      language: "English",
      interview_id: resumeId.value.trim() || null,
      resume_token: resumeToken(),
      study: collectStudy(),
    }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "Could not start the interview.");
  return payload;
}

function renderTranscriptItem(item) {
  let node = transcriptItems.get(item.id);
  if (!node) {
    node = document.createElement("li");
    node.className = `transcript-item ${item.role}`;
    node.innerHTML = `<span class="transcript-role"></span><p></p>`;
    transcript.append(node);
    transcriptItems.set(item.id, node);
  }
  node.querySelector(".transcript-role").textContent = item.role === "agent" ? "Interviewer" : "You";
  node.querySelector("p").textContent = item.text;
  transcriptEmpty.hidden = transcriptItems.size > 0;
  transcriptCount.textContent = `${transcriptItems.size} ${transcriptItems.size === 1 ? "turn" : "turns"}`;
}

function addTranscript(role, text, id = `${role}-${Date.now()}`) {
  if (!text.trim()) return;
  renderTranscriptItem({ id, role, text: text.trim() });
}

function currentAgentState() {
  return agentParticipant?.attributes?.["lk.agent.state"] || "thinking";
}

function refreshTurnState() {
  if (recordingActive) {
    setTurn("listening");
    return;
  }
  const state = currentAgentState();
  if (state === "speaking") setTurn("speaking");
  else if (state === "thinking") setTurn("thinking");
  else setTurn("thinking");
}

function handleAgentState(participant) {
  agentParticipant = participant;
  if (!recordingActive) recordButton.disabled = false;
  refreshTurnState();
}

function attachRemoteAudio(track) {
  if (track.kind !== Track.Kind.Audio) return;
  const element = track.attach();
  element.autoplay = true;
  document.body.append(element);
}

function bindAgent(participant) {
  agentParticipant = participant;
  handleAgentState(participant);
}

function showLiveView() {
  setupView.hidden = true;
  liveView.hidden = false;
  document.querySelector("#live-title").focus();
  liveView.scrollIntoView({ behavior: "smooth", block: "start" });
}

function resetTranscript() {
  transcriptItems.clear();
  transcript.replaceChildren();
  transcriptEmpty.hidden = false;
  transcriptCount.textContent = "No turns yet";
}

async function callRpc(method, payload = "") {
  if (!agentParticipant?.identity) throw new Error("Agent is not connected");
  return room.localParticipant.performRpc({
    destinationIdentity: agentParticipant.identity,
    method,
    payload,
    responseTimeout: method === "end_turn" ? 10000 : 5000,
  });
}

async function startRecording() {
  if (!agentParticipant?.identity) return;
  try {
    await callRpc("start_turn");
    await room.localParticipant.setMicrophoneEnabled(true);
    micEnabled = true;
    recordingActive = true;
    recordButton.textContent = "Stop & send";
    recordButton.classList.add("recording");
    showLiveMessage("");
    setTurn("listening", "Recording... Press Stop & send when finished.");
  } catch {
    showLiveMessage("Could not start recording. Please try again.");
  }
}

async function stopRecording() {
  if (!agentParticipant?.identity) return;
  try {
    await callRpc("end_turn");
  } catch {
    showLiveMessage("Could not send answer. Please try again.");
    return;
  }
  try {
    await room.localParticipant.setMicrophoneEnabled(false);
  } catch {
    // mic may already be disabled
  }
  micEnabled = false;
  recordingActive = false;
  recordButton.textContent = "Record answer";
  recordButton.classList.remove("recording");
  setTurn("thinking", "Processing your answer.");
}

async function toggleRecord() {
  if (recordingActive) await stopRecording();
  else await startRecording();
}

async function startInterview() {
  startButton.disabled = true;
  showSetupMessage("");
  setTurn("thinking", "Connecting you to the interviewer.");

  try {
    const session = await requestSession();
    currentInterviewId = session.interview_id;
    currentDownloadToken = session.download_token;
    localStorage.setItem(`research-resume-token:${currentInterviewId}`, currentDownloadToken);
    interviewId.value = currentInterviewId;
    copyButton.disabled = false;
    setDownloadState();
    resetTranscript();
    recordingNotice.textContent = session.recording_enabled
      ? "This interview is being recorded according to the study settings."
      : "Audio recording and full transcript storage are off. The study setup and confirmed research answers are saved to the local study record.";
    showLiveView();

    room = new Room({ adaptiveStream: true, dynacast: true });
    room.on(RoomEvent.TrackSubscribed, attachRemoteAudio);
    room.on(RoomEvent.ParticipantConnected, (participant) => {
      if (participant.isAgent) bindAgent(participant);
    });
    room.on(RoomEvent.ParticipantAttributesChanged, (_changed, participant) => {
      if (participant?.isAgent) bindAgent(participant);
    });
    room.on(RoomEvent.Disconnected, () => {
      setStatus("Interview ended");
      recordingActive = false;
      micEnabled = false;
      recordButton.disabled = true;
      recordButton.textContent = "Record answer";
      recordButton.classList.remove("recording");
      setTurn("thinking", "This interview has ended. Download the record below.");
      endButton.hidden = true;
      newInterviewButton.hidden = false;
    });
    room.registerTextStreamHandler("lk.transcription", async (reader, participantInfo) => {
      try {
        const participantIdentity = typeof participantInfo === "string" ? participantInfo : participantInfo?.identity;
        const participant = participantIdentity ? room.getParticipantByIdentity(participantIdentity) : undefined;
        const isAgent = Boolean(participant?.identity === agentParticipant?.identity || participant?.isAgent || participantIdentity === agentParticipant?.identity);
        const id = reader.info.attributes?.["lk.segment_id"] || reader.info.id || `${isAgent ? "agent" : "user"}-${Date.now()}`;
        let text = "";
        for await (const chunk of reader) {
          text += chunk;
          addTranscript(isAgent ? "agent" : "user", text, id);
        }
        if (!isAgent && !recordingActive) setTurn("thinking");
      } catch {
        showLiveMessage("Live transcription is temporarily unavailable. The interview can continue.");
      }
    });

    await room.connect(session.url, session.token);
    for (const participant of room.remoteParticipants.values()) {
      if (participant.isAgent) bindAgent(participant);
    }
    setStatus("Interview in progress", true);
    refreshTurnState();
  } catch (error) {
    setupView.hidden = false;
    liveView.hidden = true;
    showSetupMessage(error.message || "Could not access your microphone.");
    startButton.disabled = false;
  }
}

function endInterview() {
  room?.disconnect();
}

function startNewInterview() {
  room?.disconnect();
  window.scrollTo({ top: 0, behavior: "smooth" });
  window.location.reload();
}

async function copyInterviewId() {
  if (!currentInterviewId) return;
  await navigator.clipboard.writeText(currentInterviewId);
  copyButton.textContent = "Copied";
  window.setTimeout(() => { copyButton.textContent = "Copy"; }, 1200);
}

async function downloadResults(format) {
  const response = await fetch(`/api/interviews/${encodeURIComponent(currentInterviewId)}/export/${format}`, {
    headers: { "X-Download-Token": currentDownloadToken },
  });
  if (!response.ok) {
    showLiveMessage("Results are not available yet.");
    return;
  }
  const blob = await response.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${currentInterviewId}.${format}`;
  link.click();
  URL.revokeObjectURL(link.href);
}

startButton.addEventListener("click", startInterview);
endButton.addEventListener("click", endInterview);
recordButton.addEventListener("click", toggleRecord);
newInterviewButton.addEventListener("click", startNewInterview);
copyButton.addEventListener("click", copyInterviewId);
downloadJson.addEventListener("click", () => downloadResults("json"));
downloadCsv.addEventListener("click", () => downloadResults("csv"));
