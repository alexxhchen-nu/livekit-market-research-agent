import {
  Room,
  RoomEvent,
  Track,
} from "https://cdn.jsdelivr.net/npm/livekit-client@2.16.0/+esm";

const startButton = document.querySelector("#start");
const endButton = document.querySelector("#end");
const copyButton = document.querySelector("#copy-id");
const status = document.querySelector("#connection-status");
const dot = document.querySelector("#connection-dot");
const message = document.querySelector("#message");
const interviewId = document.querySelector("#interview-id");
const resumeId = document.querySelector("#resume-id");
const downloadJson = document.querySelector("#download-json");
const downloadCsv = document.querySelector("#download-csv");
const languageButtons = [...document.querySelectorAll(".language")];

const studyFields = {
  topic: "#study-topic",
  client_context: "#study-client",
  target_audience: "#study-audience",
  objective: "#study-objective",
  questions: "#study-questions",
};

let language = "English";
let room;
let currentInterviewId;
let currentDownloadToken;

function setStatus(text, connected = false) {
  status.textContent = text;
  dot.classList.toggle("connected", connected);
}

function showMessage(text) {
  message.textContent = text;
}

function selectLanguage(button) {
  language = button.dataset.language;
  languageButtons.forEach((item) => item.classList.toggle("selected", item === button));
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
      language,
      interview_id: resumeId.value.trim() || null,
      resume_token: resumeToken(),
      study: collectStudy(),
    }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "Could not start the interview.");
  return payload;
}

function setDownloadState() {
  const ready = Boolean(currentInterviewId && currentDownloadToken);
  downloadJson.disabled = !ready;
  downloadCsv.disabled = !ready;
}

async function downloadResults(format) {
  const response = await fetch(`/api/interviews/${encodeURIComponent(currentInterviewId)}/export/${format}`, {
    headers: { "X-Download-Token": currentDownloadToken },
  });
  if (!response.ok) {
    showMessage(response.status === 401 ? "This interview's download token is invalid." : "Results are not available yet.");
    return;
  }
  const blob = await response.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${currentInterviewId}.${format}`;
  link.click();
  URL.revokeObjectURL(link.href);
}

function attachRemoteAudio(track) {
  if (track.kind !== Track.Kind.Audio) return;
  const element = track.attach();
  element.autoplay = true;
  document.body.append(element);
}

async function startInterview() {
  startButton.disabled = true;
  showMessage("");
  setStatus("Connecting microphone");

  try {
    const session = await requestSession();
    currentInterviewId = session.interview_id;
    currentDownloadToken = session.download_token;
    localStorage.setItem(`research-resume-token:${currentInterviewId}`, currentDownloadToken);
    interviewId.value = currentInterviewId;
    copyButton.disabled = false;
    setDownloadState();

    room = new Room({ adaptiveStream: true, dynacast: true });
    room.on(RoomEvent.TrackSubscribed, attachRemoteAudio);
    room.on(RoomEvent.Disconnected, () => {
      setStatus("Interview ended");
      endButton.hidden = true;
      startButton.hidden = false;
      startButton.disabled = false;
    });

    await room.connect(session.url, session.token);
    await room.localParticipant.setMicrophoneEnabled(true);
    setStatus("Interview in progress", true);
    startButton.hidden = true;
    endButton.hidden = false;
  } catch (error) {
    setStatus("Could not connect");
    showMessage(error.message || "Could not access your microphone.");
    startButton.disabled = false;
  }
}

function endInterview() {
  room?.disconnect();
}

async function copyInterviewId() {
  if (!currentInterviewId) return;
  await navigator.clipboard.writeText(currentInterviewId);
  copyButton.textContent = "Copied";
  window.setTimeout(() => { copyButton.textContent = "Copy"; }, 1200);
}

languageButtons.forEach((button) => button.addEventListener("click", () => selectLanguage(button)));
startButton.addEventListener("click", startInterview);
endButton.addEventListener("click", endInterview);
copyButton.addEventListener("click", copyInterviewId);
downloadJson.addEventListener("click", () => downloadResults("json"));
downloadCsv.addEventListener("click", () => downloadResults("csv"));
