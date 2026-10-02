import assert from 'node:assert/strict';
import test from 'node:test';
import {hasUnverifiedRecordedDeadline, opportunityTiming}
  from '../src/sinter/web/campaigns.js';

const row = values => Object.freeze({status: 'researching', application_window: 'unknown',
  deadline: '2026-10-06', window_checked_at: '', ...values});

test('unknown current window retains a known closing date without claiming verification', () => {
  for (const deadline of ['2000-01-02', '2099-01-02']) {
    const item = row({deadline});
    assert.equal(hasUnverifiedRecordedDeadline(item), true);
    assert.match(opportunityTiming(item), /^Recorded closing date · /);
    assert.match(opportunityTiming(item), /Application window not verified$/);
    assert.doesNotMatch(opportunityTiming(item), /checked|passed|eligible/i);
    assert.equal(item.application_window, 'unknown');
    assert.equal(item.window_checked_at, '');
  }
});

test('unknown date stays explicit without inventing a date or source check', () => {
  const item = row({deadline: ''});
  assert.equal(hasUnverifiedRecordedDeadline(item), false);
  assert.equal(opportunityTiming(item), 'Application window not verified');
});

test('source record dates do not verify an unknown application window', () => {
  const item = row({window_checked_at: '2026-10-02'});
  assert.equal(hasUnverifiedRecordedDeadline(item), true);
  assert.match(opportunityTiming(item), /Application window not verified$/);
  assert.doesNotMatch(opportunityTiming(item), /checked/);
});

test('unknown to fixed to rolling transitions never duplicate the recorded date fact', () => {
  for (const application_window of ['unknown', 'fixed', 'rolling', 'unknown']) {
    const item = row({application_window});
    assert.equal(hasUnverifiedRecordedDeadline(item), application_window === 'unknown');
    if (application_window === 'rolling') {
      assert.equal(opportunityTiming(item), 'Rolling · source check needed');
    }
  }
  assert.equal(hasUnverifiedRecordedDeadline(row({deadline: ''})), false);
  assert.equal(hasUnverifiedRecordedDeadline(row({deadline: '2026-10-07'})), true);
});

test('fixed, legacy fixed, rolling, closed and submitted meanings are retained', () => {
  assert.match(opportunityTiming(row({application_window: 'fixed', deadline: '2099-01-02'})),
    /^Recorded closing date · /);
  assert.match(opportunityTiming(row({application_window: 'fixed', deadline: '2000-01-02'})),
    /^Recorded closing date passed · confirm current status/);
  assert.equal(opportunityTiming(row({application_window: 'fixed', deadline: ''})), 'Closing date needed');
  assert.equal(hasUnverifiedRecordedDeadline(row({application_window: undefined})), false);
  assert.equal(opportunityTiming(row({application_window: 'rolling', window_checked_at: ''})),
    'Rolling · source check needed');
  assert.match(opportunityTiming(row({application_window: 'rolling', window_checked_at: '2026-10-02'})),
    /^Rolling · checked /);
  for (const status of ['closed', 'submitted']) {
    assert.equal(hasUnverifiedRecordedDeadline(row({status})), false);
    assert.doesNotMatch(opportunityTiming(row({status})), /not verified/);
  }
  assert.equal(opportunityTiming(row({status: 'closed', deadline: ''})), 'Recorded closed');
  assert.equal(opportunityTiming(row({status: 'submitted', deadline: ''})), 'Recorded submitted');
});

test('all status/window/date combinations remain presentation-only', () => {
  for (const status of ['researching', 'open', 'upcoming', 'clarification', 'paused', 'not_pursuing', 'closed', 'submitted']) {
    for (const application_window of ['unknown', 'fixed', 'rolling']) {
      for (const deadline of ['', '2000-01-02', '2099-01-02']) {
        const item = row({status, application_window, deadline});
        const before = JSON.stringify(item);
        opportunityTiming(item);
        assert.equal(hasUnverifiedRecordedDeadline(item), Boolean(deadline)
          && application_window === 'unknown' && !['closed', 'submitted'].includes(status));
        assert.equal(JSON.stringify(item), before);
      }
    }
  }
  assert.match(opportunityTiming(row({status: 'not_pursuing'})),
    /^Not pursuing · recorded programme closing date/);
});
