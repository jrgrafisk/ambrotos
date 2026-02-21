/* ══════════════════════════════════════════════════════
   Ambrotos – frontend
   ══════════════════════════════════════════════════════ */

let calendar;
let allEvents = [];   // local cache of events

/* ─── Bootstrap ────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
  initCalendar();
  initChat();
  initModal();
});

/* ══════════════════════════════════════════════════════
   Calendar
   ══════════════════════════════════════════════════════ */

function initCalendar() {
  const el = document.getElementById('calendar');
  calendar = new FullCalendar.Calendar(el, {
    initialView: 'dayGridMonth',
    locale: 'da',
    firstDay: 1,          // Monday first
    headerToolbar: {
      left:   'prev,next today',
      center: 'title',
      right:  'dayGridMonth,dayGridWeek',
    },
    buttonText: {
      today: 'I dag',
      month: 'Måned',
      week:  'Uge',
    },
    events: fetchEvents,
    eventClick: onEventClick,
    dateClick:  onDateClick,
    dayMaxEvents: 4,
    height: 'auto',
    eventDidMount(info) {
      info.el.title = info.event.extendedProps.username;
    },
  });
  calendar.render();
}

/* Fetch events and cache them locally */
async function fetchEvents(fetchInfo, successCallback, failureCallback) {
  try {
    const resp = await fetch('/api/events');
    allEvents = await resp.json();
    successCallback(allEvents);
  } catch (err) {
    console.error('Event fetch error:', err);
    failureCallback(err);
  }
}

function refreshCalendar() {
  if (calendar) calendar.refetchEvents();
}

/* ── Event / date click ──────────────────────────────── */

function onEventClick(info) {
  showDateModal(info.event.startStr);
}

function onDateClick(info) {
  showDateModal(info.dateStr);
}

/* ══════════════════════════════════════════════════════
   Modal
   ══════════════════════════════════════════════════════ */

function initModal() {
  document.getElementById('modalClose').addEventListener('click', closeModal);
  document.getElementById('modalOverlay').addEventListener('click', e => {
    if (e.target === document.getElementById('modalOverlay')) closeModal();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
  });
}

function showDateModal(dateStr) {
  /* Format the date in Danish */
  const dateObj = new Date(dateStr + 'T12:00:00');
  const formatted = dateObj.toLocaleDateString('da-DK', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
  document.getElementById('modalDate').textContent =
    formatted.charAt(0).toUpperCase() + formatted.slice(1);

  /* Filter cached events for this date */
  const dayEvents = allEvents.filter(e => e.start === dateStr);
  const body = document.getElementById('modalBody');

  if (dayEvents.length === 0) {
    body.innerHTML = '<p class="modal-empty">Ingen er utilgængelige denne dag.</p>';
  } else {
    body.innerHTML = dayEvents.map(ev => `
      <div class="modal-member">
        <span class="modal-dot" style="background:${ev.color}"></span>
        <span class="modal-member-name">
          ${escapeHtml(ev.extendedProps.username)}
          ${ev.extendedProps.isOwn ? '<span class="modal-member-you">(dig)</span>' : ''}
        </span>
        ${ev.extendedProps.isOwn
          ? `<button class="btn btn-sm btn-danger" onclick="deleteDateViaChat('${dateStr}')">Slet</button>`
          : ''}
      </div>
    `).join('');
  }

  /* Actions for the current user */
  const hasOwn = dayEvents.some(e => e.extendedProps.isOwn);
  const actions = document.createElement('div');
  actions.className = 'modal-actions';

  if (!hasOwn) {
    const addBtn = document.createElement('button');
    addBtn.className = 'btn btn-primary btn-full';
    addBtn.textContent = 'Markér mig som utilgængelig';
    addBtn.onclick = () => addDateViaChat(dateStr);
    actions.appendChild(addBtn);
  }

  body.appendChild(actions);

  document.getElementById('modalOverlay').style.display = 'flex';
}

function closeModal() {
  document.getElementById('modalOverlay').style.display = 'none';
}

/* Called from modal "Slet" button */
async function deleteDateViaChat(dateStr) {
  closeModal();
  await sendChatMessage(`slet ${dateStr}`);
}

/* Called from modal "Markér mig" button */
async function addDateViaChat(dateStr) {
  closeModal();
  await sendChatMessage(`Jeg kan ikke den ${dateStr}`);
}

/* ══════════════════════════════════════════════════════
   Chat
   ══════════════════════════════════════════════════════ */

function initChat() {
  const input   = document.getElementById('chatInput');
  const sendBtn = document.getElementById('chatSend');

  sendBtn.addEventListener('click', handleSend);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  });
}

function handleSend() {
  const input = document.getElementById('chatInput');
  const text  = input.value.trim();
  if (!text) return;
  input.value = '';
  sendChatMessage(text);
}

async function sendChatMessage(message) {
  addBubble(message, 'user');
  const typing = addTypingIndicator();
  setSendDisabled(true);

  try {
    const resp = await fetch('/api/chat', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ message }),
    });

    const data = await resp.json();
    removeTypingIndicator(typing);

    if (data.error) {
      addBubble(`Fejl: ${data.error}`, 'ai');
    } else {
      addBubble(data.response, 'ai');
      if (data.added?.length || data.deleted?.length) {
        refreshCalendar();
      }
    }
  } catch (err) {
    removeTypingIndicator(typing);
    addBubble('Fejl: Kunne ikke forbinde til serveren. Prøv igen.', 'ai');
  } finally {
    setSendDisabled(false);
    document.getElementById('chatInput').focus();
  }
}

/* ── Chat helpers ────────────────────────────────────── */

function addBubble(text, type) {
  const container = document.getElementById('chatMessages');
  const wrap = document.createElement('div');
  wrap.className = `chat-message ${type}`;
  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble';
  bubble.textContent = text;
  wrap.appendChild(bubble);
  container.appendChild(wrap);
  container.scrollTop = container.scrollHeight;
  return wrap;
}

function addTypingIndicator() {
  const container = document.getElementById('chatMessages');
  const wrap = document.createElement('div');
  wrap.className = 'chat-message ai typing';
  wrap.innerHTML = `
    <div class="chat-bubble">
      <div class="typing-dots">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
    </div>`;
  container.appendChild(wrap);
  container.scrollTop = container.scrollHeight;
  return wrap;
}

function removeTypingIndicator(el) {
  if (el?.parentNode) el.remove();
}

function setSendDisabled(disabled) {
  document.getElementById('chatSend').disabled  = disabled;
  document.getElementById('chatInput').disabled = disabled;
}

/* ── Utilities ───────────────────────────────────────── */

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
