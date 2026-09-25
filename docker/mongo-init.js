// =============================================================================
// mongo-init.js — first-run bootstrap for a fresh database
// =============================================================================
// MongoDB runs every file in /docker-entrypoint-initdb.d exactly once, and only
// while /data/db is empty. That is the only moment this can run, which is what
// makes `docker compose up` self-sufficient.
//
// Mounted by docker-compose.yml as:
//   ./docker/mongo-init.js:/docker-entrypoint-initdb.d/01-init.js:ro
//
// The application user is created INSIDE the application database (not in
// `admin`), so the backend can connect with just the database in the URI:
//   mongodb://rag:ragpassword@mongo:27017/responsible_rag
// =============================================================================

const dbName =
  process.env.MONGO_DB || process.env.MONGO_INITDB_DATABASE || 'responsible_rag';
const appUser = process.env.MONGO_APP_USER || 'rag';
const appPassword = process.env.MONGO_APP_PASSWORD || 'ragpassword';

const appDb = db.getSiblingDB(dbName);

// Safety guard: this bootstrap is for EMPTY databases only. MongoDB already
// skips this directory when /data/db is non-empty; the guard also protects
// against running this file by hand against a populated (production) server.
const existing = appDb
  .getCollectionNames()
  .filter((name) => !name.startsWith('system.'));
if (existing.length > 0 && process.env.MONGO_INIT_ALLOW_EXISTING !== '1') {
  print(
    `[init] REFUSING to run: '${dbName}' already holds ${existing.length} collection(s): ` +
      `${existing.join(', ')}`
  );
  print(
    '[init] Nothing was changed. Set MONGO_INIT_ALLOW_EXISTING=1 only if you truly mean to bootstrap over existing data.'
  );
  quit(1);
}

if (appDb.getUser(appUser)) {
  print(`[init] user '${appUser}' already exists in '${dbName}'`);
} else {
  appDb.createUser({
    user: appUser,
    pwd: appPassword,
    roles: [
      { role: 'readWrite', db: dbName },
      { role: 'dbAdmin', db: dbName },
    ],
  });
  print(`[init] created '${appUser}' in '${dbName}'`);
}

// Collections the application reads on a cold start, so the first request does
// not have to wait for an implicit create.
const collections = [
  'users',
  'profiles',
  'consent',
  'conversations',
  'messages',
  'feedback',
  'admin_alerts',
];

for (const name of collections) {
  if (!appDb.getCollectionNames().includes(name)) {
    appDb.createCollection(name);
    print(`[init] created collection '${dbName}.${name}'`);
  }
}

// Indexes the application depends on for correct and cheap lookups. Failures are
// reported but never fatal: a unique-index conflict must not stop mongod from
// starting, which would turn a non-data problem into an outage.
const indexes = [
  ['users', { email: 1 }, { unique: true }],
  ['profiles', { user_id: 1 }, { unique: true }],
  ['consent', { user_id: 1 }, { unique: true }],
  ['conversations', { user_id: 1, updated_at: -1 }, {}],
  ['messages', { conversation_id: 1, created_at: 1 }, {}],
];

for (const [collection, keys, options] of indexes) {
  try {
    appDb.getCollection(collection).createIndex(keys, options);
  } catch (error) {
    print(
      `[init] WARNING: could not create index on ${dbName}.${collection}: ${error.message}`
    );
  }
}
print(`[init] ready: ${dbName}`);
