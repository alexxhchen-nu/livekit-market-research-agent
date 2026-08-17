const language = document.querySelector("#language");
const startButton = document.querySelector("#start");
const form = document.querySelector("#turn-form");
const text = document.querySelector("#text");
const submitButton = document.querySelector("#submit");
const microphoneButton = document.querySelector("#microphone");
const status = document.querySelector("#status");
const transcript = document.querySelector("#transcript");

let sessionId;
let recognizing = false;
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const recognition = Recognition ? new Recognition() : null;

function showStatus(message) {
  status.textContent = message;
}

function addTurn(role, message) {
  const turn = document.createElement("p");
  const speaker = document.createElement("strong");
  speaker.textContent = `${role}: `;
  turn.append(speaker, document.createTextNode(message));
  transcript.append(turn);
}

function speak(message) {
  if (!("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(message);
  utterance.lang = language.value;
  window.speechSynthesis.speak(utterance);
}

async function request(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error("request failed");
  return response.json();
}

startButton.addEventListener("click", async () => {
  if (recognizing) recognition.stop();
  startButton.disabled = true;
  transcript.replaceChildren();
  sessionId = undefined;
  showStatus("正在创建访谈…");
  try {
    const response = await fetch("/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language: language.value }),
    });
    if (!response.ok) throw new Error("request failed");
    const result = await response.json();
    sessionId = result.session_id;
    addTurn("访谈者", result.interviewer_text);
    text.disabled = false;
    submitButton.disabled = false;
    if (recognition) microphoneButton.disabled = false;
    showStatus("访谈已开始");
    text.focus();
    speak(result.interviewer_text);
  } catch {
    startButton.disabled = false;
    showStatus("无法开始访谈，请稍后重试。");
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (recognizing) recognition.stop();
  const answer = text.value.trim();
  if (!sessionId || !answer) return;

  text.disabled = true;
  submitButton.disabled = true;
  microphoneButton.disabled = true;
  let completed = false;
  showStatus("正在提交回答…");
  try {
    const result = await request(`/sessions/${encodeURIComponent(sessionId)}/turns`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: answer }),
    });
    addTurn("您", answer);
    addTurn("访谈者", result.interviewer_text);
    text.value = "";
    const complete = result.status === "complete";
    completed = complete;
    showStatus(complete ? "访谈已完成" : "请继续回答");
    speak(result.interviewer_text);
    if (complete) {
      text.disabled = true;
      submitButton.disabled = true;
      microphoneButton.disabled = true;
      startButton.disabled = false;
    }
  } catch {
    showStatus("无法提交回答，请稍后重试。");
  } finally {
    if (!completed) {
      text.disabled = false;
      submitButton.disabled = false;
      if (recognition) microphoneButton.disabled = false;
      text.focus();
    }
  }
});

if (recognition) {
  recognition.interimResults = true;
  microphoneButton.hidden = false;

  recognition.addEventListener("start", () => {
    recognizing = true;
    microphoneButton.textContent = "停止录音";
    showStatus("正在听取语音…");
  });
  recognition.addEventListener("end", () => {
    recognizing = false;
    microphoneButton.textContent = "开始录音";
  });
  recognition.addEventListener("result", (event) => {
    let finalText = "";
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      if (event.results[i].isFinal) finalText += event.results[i][0].transcript;
    }
    if (finalText) {
      text.value = finalText;
      showStatus("语音已转为文字，请确认后提交。");
    }
  });
  recognition.addEventListener("error", () => {
    showStatus("语音识别失败，请使用文字输入。");
  });
  microphoneButton.addEventListener("click", () => {
    if (recognizing) {
      recognition.stop();
    } else {
      recognition.lang = language.value;
      recognition.start();
    }
  });
}
