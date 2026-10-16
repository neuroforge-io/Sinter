import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync} from 'node:fs';
import {markdown} from '../src/sinter/web/markdown.js';

const fixture = JSON.parse(readFileSync(new URL('fixtures/literal_paragraph.v1.json', import.meta.url)));

// Inert structure checks supplement actual browser/copy/export qualification.
class TestNode {
  constructor(tag, value = '') { this.tagName = tag; this.value = value; this.children = []; }
  append(...nodes) { this.children.push(...nodes); }
  setAttribute() {}
  get textContent() {
    if (this.tagName === 'BR') return '\n';
    return this.value + this.children.map(child => child.textContent).join('');
  }
}

test('shared plain paragraphs stay literal in the browser renderer', () => {
  const previousNode = globalThis.Node, previousDocument = globalThis.document;
  globalThis.Node = TestNode;
  globalThis.document = {createElement: tag => new TestNode(tag.toUpperCase()),
    createTextNode: text => new TestNode('#text', text)};
  try {
    for (const [raw, encoded] of fixture.cases) {
      const result = markdown(encoded);
      assert.equal(result.textContent, raw);
      assert.equal(result.children.length, 1);
      assert.equal(result.children[0].tagName, 'P');
      assert.ok(result.children[0].children.every(node => node.tagName === '#text'));
    }
    const result = markdown(fixture.cases.map(([, encoded]) => encoded).join('\n'));
    assert.equal(result.textContent, fixture.cases.map(([raw]) => raw).join('\n'));
    assert.equal(result.children.length, 1);
    assert.ok(result.children[0].children.every(node => ['#text', 'BR'].includes(node.tagName)));
  } finally {
    globalThis.Node = previousNode; globalThis.document = previousDocument;
  }
});
