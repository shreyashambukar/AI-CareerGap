/**
 * roadmap.js — AI CareerGap Roadmap Tracker
 *
 * State is kept in memory only for the current page load.
 * Checkboxes start unchecked and notes start blank every time
 * the results page is opened or refreshed.
 *
 * Any previously saved localStorage keys are cleared on load
 * so old persisted data does not bleed into a new session.
 */

(function () {
  'use strict';

  // ----- Clear any old persisted roadmap data -----
  try {
    const toRemove = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith('careergap_roadmap_')) toRemove.push(k);
    }
    toRemove.forEach(function (k) { localStorage.removeItem(k); });
  } catch (_) { /* localStorage may be blocked — ignore */ }

  // ----- Read embedded data -----
  const dataEl = document.getElementById('roadmap-data');
  if (!dataEl) return;

  let roadmapData;
  try {
    roadmapData = JSON.parse(dataEl.textContent);
  } catch (e) {
    console.warn('AI CareerGap: could not parse roadmap data', e);
    return;
  }

  const { tasks } = roadmapData;
  const container  = document.getElementById('roadmap-tasks');

  if (!tasks || tasks.length === 0) {
    if (container) {
      container.innerHTML = '<p class="empty-state">No skill gaps to track — you\'re already qualified! 🎉</p>';
    }
    return;
  }

  // ----- In-memory state (reset on every page load) -----
  // state[taskId] = { completed: bool, note: string }
  const state = {};

  const progressBar  = document.getElementById('roadmap-progress-bar');
  const progressText = document.getElementById('roadmap-progress-text');

  // ----- Progress update -----
  function updateProgress() {
    const total = tasks.length;
    const done  = tasks.filter(function (t) { return state[t.id] && state[t.id].completed; }).length;
    const pct   = total > 0 ? Math.round((done / total) * 100) : 0;

    if (progressBar) {
      progressBar.style.width = pct + '%';
      progressBar.className   = 'progress-bar ' + (pct >= 70 ? 'high' : pct >= 40 ? 'medium' : 'low');
      progressBar.setAttribute('aria-valuenow', pct);
    }
    if (progressText) {
      progressText.textContent = done + ' of ' + total + ' tasks completed (' + pct + '%)';
    }
  }

  // ----- Render tasks -----
  function renderTasks() {
    if (!container) return;
    container.innerHTML = '';

    tasks.forEach(function (task, idx) {
      /*
       * Layout: [ checkbox ] [ step label + task title ]
       *                      [ optional note input     ]
       *
       * The checkbox is vertically centred with the task title.
       */
      const wrapper = document.createElement('div');
      wrapper.className = 'roadmap-task';
      wrapper.setAttribute('role', 'listitem');

      // Checkbox — aligned with the title line
      const cbId = 'cb-' + task.id;
      const cb   = document.createElement('input');
      cb.type  = 'checkbox';
      cb.id    = cbId;
      cb.setAttribute('aria-labelledby', 'title-' + task.id);

      // Body
      const body = document.createElement('div');
      body.className = 'roadmap-task-body';

      const stepNum = document.createElement('div');
      stepNum.className = 'roadmap-week';
      stepNum.textContent = 'Step ' + (idx + 1) +
        (task.skill && task.skill !== 'Portfolio' ? ' \u2014 ' + task.skill : '');

      const title = document.createElement('label');
      title.className = 'roadmap-task-title';
      title.id        = 'title-' + task.id;
      title.htmlFor   = cbId;
      title.textContent = task.label;

      const noteInput = document.createElement('input');
      noteInput.type        = 'text';
      noteInput.className   = 'roadmap-note-input';
      noteInput.placeholder = 'Optional: add a note or evidence link\u2026';
      noteInput.setAttribute('aria-label', 'Evidence note for: ' + task.label);

      body.appendChild(stepNum);
      body.appendChild(title);
      body.appendChild(noteInput);
      wrapper.appendChild(cb);
      wrapper.appendChild(body);
      container.appendChild(wrapper);

      // ----- Event listeners (update in-memory state only) -----
      cb.addEventListener('change', function () {
        if (!state[task.id]) state[task.id] = { completed: false, note: '' };
        state[task.id].completed = cb.checked;

        wrapper.classList.toggle('completed', cb.checked);
        title.classList.toggle('done', cb.checked);
        updateProgress();
      });

      noteInput.addEventListener('input', function () {
        if (!state[task.id]) state[task.id] = { completed: false, note: '' };
        state[task.id].note = noteInput.value;
      });
    });

    updateProgress(); // initialise at 0%
  }

  renderTasks();

})();
