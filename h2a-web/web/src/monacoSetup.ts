// Bundle Monaco locally (no CDN) so the diff editor works offline, and wire the
// base web worker for Vite. Imported by the lazy-loaded Diff component only, so
// Monaco stays out of the main bundle until the Diff tab is opened.
import * as monaco from 'monaco-editor';
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';
import { loader } from '@monaco-editor/react';

(self as any).MonacoEnvironment = { getWorker: () => new editorWorker() };
loader.config({ monaco });
