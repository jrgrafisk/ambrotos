/* ══════════════════════════════════════════════════════
   Ambrotos – frontend
   ══════════════════════════════════════════════════════ */

let calendar;
let allEvents     = [];   // local cache of FullCalendar events
let eventMode     = false;
let currentEventId = null;
let pendingEventDate = null;

/* ─── Bootstrap ─────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
  initCalendar();
  initModals();
  loadUpcomingEvents();
});

/* ══════════════════════════════════════════════════════
   Calendar
   ══════════════════════════════════════════════════════ */

function initCalendar() {
  const el = document.getElementById('calendar');
  calendar = new FullCalendar.Calendar(el, {
    initialView: 'dayGridMonth',
    locale: 'da',
    firstDay: 1,
    headerToolbar: {
      left:   'prev,next today',
      center: 'title',
      right:  'dayGridMonth,dayGridThreeMonth,dayGridYear,dayGridWeek',
    },
    views: {
      dayGridThreeMonth: {
        type: 'dayGrid',
        duration: { months: 3 },
        buttonText: '3 måneder',
      },
      dayGridYear: {
        type: 'dayGrid',
        duration: { months: 12 },
        buttonText: 'År',
      },
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
    eventsSet() {
      setTimeout(renderUnavailCircles, 0);
    },
    datesSet() {
      document.querySelectorAll('.day-unavail-circles').forEach(el => el.remove());
    },
    eventDidMount(info) {
      const props = info.event.extendedProps;
      if (props.isGroupEvent) {
        info.el.title = info.event.title;
      } else if (props.isHoliday) {
        info.el.title = props.holidayDescription
          ? `${props.holidayName} — ${props.holidayDescription}`
          : props.holidayName;
      }
    },
  });
  calendar.render();
}

async function fetchEvents(fetchInfo, successCallback, failureCallback) {
  try {
    const resp = await fetch('/api/events');
    const data  = await resp.json();
    allEvents   = data;
    // Unavailability events are hidden from FullCalendar's bar rendering;
    // circles are injected into day cells by renderUnavailCircles().
    successCallback(data.map(e =>
      (!e.extendedProps.isHoliday && !e.extendedProps.isGroupEvent)
        ? { ...e, display: 'none' }
        : e
    ));
  } catch (err) {
    console.error('Event fetch error:', err);
    failureCallback(err);
  }
}

function renderUnavailCircles() {
  document.querySelectorAll('.day-unavail-circles').forEach(el => el.remove());
  document.querySelectorAll('.fc-daygrid-day').forEach(cell => {
    const dateStr = cell.dataset.date;
    if (!dateStr) return;
    const unavail = allEvents.filter(e =>
      e.start === dateStr && !e.extendedProps?.isHoliday && !e.extendedProps?.isGroupEvent
    );
    if (!unavail.length) return;

    const container = document.createElement('div');
    container.className = 'day-unavail-circles';
    const MAX = 6;
    unavail.slice(0, MAX).forEach(ev => {
      const circle = document.createElement('span');
      circle.className = 'day-avatar day-avatar-user';
      circle.style.background = ev.color;
      circle.title = ev.extendedProps.username;
      circle.textContent = getInitials(ev.extendedProps.username);
      container.appendChild(circle);
    });
    if (unavail.length > MAX) {
      const more = document.createElement('span');
      more.className = 'day-avatar day-avatar-more';
      more.textContent = `+${unavail.length - MAX}`;
      container.appendChild(more);
    }
    const eventsArea = cell.querySelector('.fc-daygrid-day-events');
    if (eventsArea) eventsArea.prepend(container);
    else cell.append(container);
  });
}

function refreshCalendar() {
  if (calendar) calendar.refetchEvents();
}

/* ── Event mode toggle ───────────────────────────────── */

function toggleEventMode() {
  eventMode = !eventMode;
  const btn  = document.getElementById('eventModeBtn');
  const hint = document.getElementById('eventModeHint');
  const cal  = document.getElementById('calendar');
  if (eventMode) {
    btn.classList.add('active');
    btn.textContent = '✕ Annuller';
    hint.style.display = 'inline';
    cal.classList.add('event-mode-active');
  } else {
    btn.classList.remove('active');
    btn.textContent = '+ Opret event';
    hint.style.display = 'none';
    cal.classList.remove('event-mode-active');
  }
}

/* ── Event / date click ──────────────────────────────── */

function onEventClick(info) {
  const props = info.event.extendedProps;
  if (props.isGroupEvent) {
    showEventDetailModal(props.eventId);
  } else {
    showDateModal(info.event.startStr);
  }
}

function onDateClick(info) {
  if (eventMode) {
    openEventCreateModal(info.dateStr);
  } else {
    showDateModal(info.dateStr);
  }
}

/* ══════════════════════════════════════════════════════
   Date modal (unavailability)
   ══════════════════════════════════════════════════════ */

function initModals() {
  document.getElementById('modalClose').addEventListener('click', closeModal);
  document.getElementById('modalOverlay').addEventListener('click', e => {
    if (e.target === document.getElementById('modalOverlay')) closeModal();
  });
  document.getElementById('eventCreateOverlay').addEventListener('click', e => {
    if (e.target === document.getElementById('eventCreateOverlay')) closeEventCreateModal();
  });
  document.getElementById('eventDetailOverlay').addEventListener('click', e => {
    if (e.target === document.getElementById('eventDetailOverlay')) closeEventDetailModal();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      closeModal();
      closeEventCreateModal();
      closeEventDetailModal();
    }
  });
  document.getElementById('commentInput').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitComment(); }
  });
  document.getElementById('eventTitle').addEventListener('keydown', e => {
    if (e.key === 'Enter') submitEventCreate();
  });
}

function showDateModal(dateStr) {
  const dateObj = new Date(dateStr + 'T12:00:00');
  const formatted = dateObj.toLocaleDateString('da-DK', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  });
  document.getElementById('modalDate').textContent =
    formatted.charAt(0).toUpperCase() + formatted.slice(1);

  const dayEvents   = allEvents.filter(e => e.start === dateStr);
  const holidayEvts = dayEvents.filter(e => e.extendedProps.isHoliday);
  const unavailEvts = dayEvents.filter(e => !e.extendedProps.isHoliday && !e.extendedProps.isGroupEvent);
  const body        = document.getElementById('modalBody');

  let html = '';

  if (holidayEvts.length > 0) {
    html += holidayEvts.map(ev => `
      <div class="modal-holiday">
        <span class="modal-holiday-icon">🎉</span>
        <div>
          <div class="modal-holiday-name">${escapeHtml(ev.extendedProps.holidayName)}</div>
          ${ev.extendedProps.holidayDescription
            ? `<div class="modal-holiday-desc">${escapeHtml(ev.extendedProps.holidayDescription)}</div>`
            : ''}
        </div>
      </div>
    `).join('');
  }

  if (unavailEvts.length === 0) {
    html += '<p class="modal-empty">Ingen er utilgængelige denne dag.</p>';
  } else {
    html += unavailEvts.map(ev => `
      <div class="modal-member">
        <span class="modal-dot" style="background:${ev.color}"></span>
        <span class="modal-member-name">
          ${escapeHtml(ev.extendedProps.username)}
          ${ev.extendedProps.isOwn ? '<span class="modal-member-you">(dig)</span>' : ''}
        </span>
        ${ev.extendedProps.isOwn
          ? `<button class="btn btn-sm btn-danger" onclick="toggleUnavailable('${dateStr}')">Slet</button>`
          : ''}
      </div>
    `).join('');
  }

  body.innerHTML = html;

  const hasOwn = unavailEvts.some(e => e.extendedProps.isOwn);
  if (!hasOwn) {
    const actions = document.createElement('div');
    actions.className = 'modal-actions';
    const addBtn = document.createElement('button');
    addBtn.className = 'btn btn-primary btn-full';
    addBtn.textContent = 'Markér mig som utilgængelig';
    addBtn.onclick = () => toggleUnavailable(dateStr);
    actions.appendChild(addBtn);
    body.appendChild(actions);
  }

  document.getElementById('modalOverlay').style.display = 'flex';
}

function closeModal() {
  document.getElementById('modalOverlay').style.display = 'none';
}

async function toggleUnavailable(dateStr) {
  closeModal();
  try {
    const resp = await fetch('/api/unavailable/toggle', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ date: dateStr }),
    });
    if (resp.ok) refreshCalendar();
  } catch (err) {
    console.error('Toggle unavailable error:', err);
  }
}

/* ══════════════════════════════════════════════════════
   Event create modal
   ══════════════════════════════════════════════════════ */

function openEventCreateModal(dateStr) {
  pendingEventDate = dateStr;
  const dateObj = new Date(dateStr + 'T12:00:00');
  const formatted = dateObj.toLocaleDateString('da-DK', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  });
  document.getElementById('eventCreateDate').textContent =
    formatted.charAt(0).toUpperCase() + formatted.slice(1);
  document.getElementById('eventTitle').value = '';
  document.getElementById('eventDesc').value  = '';
  document.getElementById('eventCreateOverlay').style.display = 'flex';
  setTimeout(() => document.getElementById('eventTitle').focus(), 50);
}

function closeEventCreateModal() {
  document.getElementById('eventCreateOverlay').style.display = 'none';
  pendingEventDate = null;
}

async function submitEventCreate() {
  const title = document.getElementById('eventTitle').value.trim();
  const desc  = document.getElementById('eventDesc').value.trim();
  if (!title || !pendingEventDate) return;
  try {
    const resp = await fetch('/api/group-events', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ title, description: desc, date: pendingEventDate }),
    });
    if (resp.ok) {
      closeEventCreateModal();
      if (eventMode) toggleEventMode();
      refreshCalendar();
      loadUpcomingEvents();
    }
  } catch (err) {
    console.error('Create event error:', err);
  }
}

/* ══════════════════════════════════════════════════════
   Event detail modal (with comments)
   ══════════════════════════════════════════════════════ */

async function showEventDetailModal(eventId) {
  currentEventId = eventId;
  try {
    const resp = await fetch(`/api/group-events/${eventId}`);
    if (!resp.ok) return;
    const ev = await resp.json();

    const dateObj = new Date(ev.date + 'T12:00:00');
    const formatted = dateObj.toLocaleDateString('da-DK', {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    });
    document.getElementById('eventDetailTitle').textContent   = ev.title;
    document.getElementById('eventDetailDate').textContent    =
      formatted.charAt(0).toUpperCase() + formatted.slice(1);
    const descEl = document.getElementById('eventDetailDesc');
    descEl.textContent    = ev.description || '';
    descEl.style.display  = ev.description ? '' : 'none';
    document.getElementById('eventDetailCreator').textContent = `Oprettet af ${ev.creator}`;
    document.getElementById('eventDetailActions').innerHTML   = ev.is_own
      ? `<button class="btn btn-sm btn-danger" onclick="deleteGroupEvent(${ev.id})">Slet event</button>`
      : '';

    renderAttendance(ev.attending, ev.not_attending);
    renderComments(ev.comments);
    document.getElementById('commentInput').value = '';
    document.getElementById('eventDetailOverlay').style.display = 'flex';
  } catch (err) {
    console.error('Load event error:', err);
  }
}

function closeEventDetailModal() {
  document.getElementById('eventDetailOverlay').style.display = 'none';
  currentEventId = null;
}

function renderAttendance(attending, notAttending) {
  const section = document.getElementById('eventAttendance');
  const avatarHtml = (users) => users.map(u =>
    `<div class="avatar" style="background:${u.color}" title="${escapeHtml(u.username)}">${escapeHtml(getInitials(u.username))}</div>`
  ).join('');

  section.innerHTML = `
    <div class="attendance-row">
      <span class="attendance-label attending">Kan deltage (${attending.length})</span>
      <div class="attendance-avatars">${attending.length ? avatarHtml(attending) : '<span class="attendance-none">—</span>'}</div>
    </div>
    <div class="attendance-row">
      <span class="attendance-label not-attending">Kan ikke (${notAttending.length})</span>
      <div class="attendance-avatars">${notAttending.length ? avatarHtml(notAttending) : '<span class="attendance-none">—</span>'}</div>
    </div>
  `;
}

function renderComments(comments) {
  const list = document.getElementById('eventComments');
  if (comments.length === 0) {
    list.innerHTML = '<p class="comments-empty">Ingen kommentarer endnu.</p>';
    return;
  }
  list.innerHTML = comments.map(c => `
    <div class="comment">
      <span class="comment-dot" style="background:${c.author_color}"></span>
      <div class="comment-content">
        <span class="comment-author">${escapeHtml(c.author)}</span>
        <span class="comment-time">${escapeHtml(c.created_at)}</span>
        <p class="comment-text">${escapeHtml(c.text)}</p>
      </div>
    </div>
  `).join('');
  list.scrollTop = list.scrollHeight;
}

async function submitComment() {
  const input = document.getElementById('commentInput');
  const text  = input.value.trim();
  if (!text || !currentEventId) return;
  input.value = '';
  try {
    const resp = await fetch(`/api/group-events/${currentEventId}/comments`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ text }),
    });
    if (resp.ok) {
      const evResp = await fetch(`/api/group-events/${currentEventId}`);
      if (evResp.ok) renderComments((await evResp.json()).comments);
    }
  } catch (err) {
    console.error('Comment error:', err);
  }
}

async function deleteGroupEvent(eventId) {
  if (!confirm('Slet dette event?')) return;
  try {
    const resp = await fetch(`/api/group-events/${eventId}`, { method: 'DELETE' });
    if (resp.ok) {
      closeEventDetailModal();
      refreshCalendar();
      loadUpcomingEvents();
    }
  } catch (err) {
    console.error('Delete event error:', err);
  }
}

/* ══════════════════════════════════════════════════════
   Upcoming events list
   ══════════════════════════════════════════════════════ */

async function loadUpcomingEvents() {
  const container = document.getElementById('upcomingEvents');
  try {
    const resp   = await fetch('/api/group-events');
    const events = await resp.json();
    if (events.length === 0) {
      container.innerHTML = '<p class="events-empty">Ingen kommende events.</p>';
      return;
    }
    container.innerHTML = events.map(ev => {
      const dateObj = new Date(ev.date + 'T12:00:00');
      const formatted = dateObj.toLocaleDateString('da-DK', {
        day: 'numeric', month: 'short', year: 'numeric',
      });
      const commentStr = ev.comment_count > 0
        ? ` · ${ev.comment_count} kommentar${ev.comment_count !== 1 ? 'er' : ''}`
        : '';
      return `
        <div class="event-item" onclick="showEventDetailModal(${ev.id})">
          <div class="event-item-date">${escapeHtml(formatted)}</div>
          <div class="event-item-title">${escapeHtml(ev.title)}</div>
          ${ev.description
            ? `<div class="event-item-desc">${escapeHtml(ev.description)}</div>`
            : ''}
          <div class="event-item-meta">
            ${escapeHtml(ev.creator)}${commentStr}
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    console.error('Load upcoming events error:', err);
    container.innerHTML = '<p class="events-empty">Kunne ikke indlæse events.</p>';
  }
}

/* ── Utilities ───────────────────────────────────────── */

function getInitials(name) {
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2);
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
