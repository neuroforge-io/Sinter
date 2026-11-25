/** Sinter surface for the local comprehension episode service. */
import {h, button, field, selectField, notice} from './ui.js';
import {request} from './api.js';

export function comprehensionPage() {
  const output = h('pre', {class: 'comprehension-output'});
  const status = h('p', {class: 'fine', role: 'status'}, 'No episode yet.');
  let episode = null;
  const show = value => {
    output.textContent = JSON.stringify(value, null, 2);
    if (value?.capability_id) status.textContent = `Capability ${value.capability_id}`;
    else if (value?.episode_id) {
      episode = value.episode_id;
      status.textContent = `Episode ${episode} — revision ${value.revision ?? 1}`;
    }
  };
  async function call(path, data) {
    try { show(await request(path, {data})); }
    catch (error) { show({error: error.message}); }
  }
  const create = button('Create episode', () => call('/api/comprehension/episodes', {}), 'primary');
  const lessonId = field('Lesson identity', 'text', 'dalven-1');
  const lesson = field('Multi-sentence lesson', 'textarea',
    'A dalven is a storage device.\nIts charge is the amount currently stored.\nIts capacity is the maximum amount it can hold.\nIts reserve is the minimum amount that must remain during operation.\nA draw removes an amount from the charge.\nA draw is permitted only if it preserves the reserve.\nWhen a dalven is offline, the reserve requirement does not apply.',
    'The lesson is supplied to the local comprehension service; it is not a hidden task.');
  const teach = button('Teach and inspect', () => {
    if (!episode) return show({error: 'Create an episode first.'});
    return call(`/api/comprehension/episodes/${episode}/lesson`,
      {lesson_id: lessonId.input.value, text: lesson.input.value});
  });
  const task = field('Hidden task', 'textarea',
    'A functioning dalven contains 23 units and requires a reserve of 7. How much can be drawn without violating its reserve?');
  const solve = button('Solve in the educational context', () => {
    if (!episode) return show({error: 'Create an episode first.'});
    return call(`/api/comprehension/episodes/${episode}/task`,
      {task: task.input.value});
  });
  const application = selectField('Transfer application context',
    [['inventory', 'Inventory'], ['meeting', 'Meeting'], ['workspace', 'Workspace']]);
  const transferTask = field('Transfer task', 'textarea',
    'A functioning dalven contains 41 units and requires a reserve of 9. How much can be drawn?');
  const transfer = button('Transfer capability', () => {
    if (!episode) return show({error: 'Create an episode first.'});
    return call(`/api/comprehension/episodes/${episode}/transfer`,
      {application: application.input.value, task: transferTask.input.value});
  });

  const observation = field('Observation', 'textarea',
    'The larger container contains 12 items.');
  const observe = button('Observe and update situation', () => {
    if (!episode) return show({error: 'Create an episode first.'});
    return call(`/api/comprehension/episodes/${episode}/observe`,
      {text: observation.input.value});
  });
  const question = field('Question', 'text',
    'How many items are in the smaller container?');
  const query = button('Ask the situation', () => {
    if (!episode) return show({error: 'Create an episode first.'});
    return call(`/api/comprehension/episodes/${episode}/observe`,
      {text: question.input.value});
  });
  const observationId = field('Observation ID to correct', 'text', '');
  const correction = field('Corrected observation', 'textarea',
    'Four items are moved from the larger to the smaller.');
  const correct = button('Correct observation', () => {
    if (!episode) return show({error: 'Create an episode first.'});
    return call(`/api/comprehension/episodes/${episode}/correct`,
      {observation_id: observationId.input.value, text: correction.input.value,
       reason: 'Sinter reviewer correction'});
  });
  const obligationId = field('Obligation ID', 'text', '');
  const clarification = field('Clarification value', 'text', 'larger');
  const clarify = button('Resolve clarification', () => {
    if (!episode) return show({error: 'Create an episode first.'});
    return call(`/api/comprehension/episodes/${episode}/clarify`,
      {obligation_id: obligationId.input.value, value: clarification.input.value});
  });
  const situation = button('Inspect situation', () => {
    if (!episode) return show({error: 'Create an episode first.'});
    return call(`/api/comprehension/episodes/${episode}/situation`);
  });

  return h('section', {class: 'form-panel', 'aria-label': 'Comprehension laboratory'},
    h('h2', {}, 'Comprehension laboratory'),
    notice('This surface calls the configured local comprehension service. It does not send lessons or tasks to a remote service.'),
    h('div', {class: 'button-row'}, create, status),
    h('fieldset', {}, h('legend', {}, 'Teach an unfamiliar lesson'),
      lessonId.wrap, lesson.wrap, teach),
    h('fieldset', {}, h('legend', {}, 'Solve a hidden task'),
      task.wrap, solve),
    h('fieldset', {}, h('legend', {}, 'Transfer the acquired capability'),
      application.wrap, transferTask.wrap, transfer),
    h('fieldset', {}, h('legend', {}, 'Observe, correct and clarify a situation'),
      observation.wrap, observe, question.wrap, query,
      h('div', {class: 'form-grid'}, observationId.wrap, correction.wrap),
      correct, h('div', {class: 'form-grid'}, obligationId.wrap, clarification.wrap),
      clarify, situation),
    h('label', {}, 'Evidence output'), output);
}
