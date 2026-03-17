// ── State ──────────────────────────────────────────────────────────────────

let currentAgent = null;
let agents = {};
let employees = {};
let chatHistories = {};
let agentRuntimes = {};  // per-agent runtime: { agentName: 'opus' | 'sonnet' | 'haiku' | 'cursor' }
let thinkingAgents = {};  // per-agent thinking state: { agentName: true }
let runningTasks = {};   // { taskId: { agent, role, runtime, started_at, elapsed_seconds } }
let runningTasksTimer = null;  // elapsed update timer
let sprintAutoRunState = {};   // { sprintId: { running: bool, cancelled: bool } }
let _taskCompletionResolvers = [];  // resolvers notified when any task completes
let agentDrafts = {};  // per-agent draft text: { agentName: "draft text" }

const API_BASE = (typeof location !== 'undefined' && location.origin) ? location.origin : '';
