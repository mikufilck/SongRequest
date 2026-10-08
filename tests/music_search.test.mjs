import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';

const production = new URL('../worker/music-search.mjs', import.meta.url);
const { searchSongs, searchNetease, searchQQ, mergeSongs } = await import(
  existsSync(production) ? production : new URL('../src/music_search.mjs', import.meta.url)
);

test('normalized title and artists merge platform IDs without dropping payment information', () => {
  const result = mergeSongs(
    [{ id: '123', name: 'My Song', artists: 'Singer', album: 'Album', fee: 1 }],
    [{ id: 'qq-id', name: 'my song', artists: ' singer ', album: 'Other', fee: 0 }],
  );
  assert.equal(result.length, 1);
  assert.deepEqual(result[0].platforms, ['netease', 'qq']);
  assert.equal(result[0].neteaseId, '123');
  assert.equal(result[0].qqId, 'qq-id');
  assert.equal(result[0].fee, 1);
});

test('one provider failure retains the other provider and uses encoded keywords', async () => {
  const seen = [];
  const fetcher = async (url, options) => {
    seen.push([new URL(url), options]);
    if (url.includes('music.163.com')) throw new Error('offline fixture');
    return Response.json({ data: { song: { list: [{ songmid: 'qq-1', songname: '晴天', singer: [{ name: '歌手' }], pay: { payplay: 1 } }] } } });
  };
  const result = await searchSongs(' 晴天 & 歌手 ', { fetcher });
  assert.equal(result.length, 1);
  assert.equal(result[0].qqId, 'qq-1');
  assert.equal(seen.find(([url]) => url.hostname === 'music.163.com')[0].searchParams.get('s'), '晴天 & 歌手');
  assert.equal(seen.find(([url]) => url.hostname === 'c.y.qq.com')[0].searchParams.get('w'), '晴天 & 歌手');
  assert.ok(seen.every(([, options]) => options.signal instanceof AbortSignal));
});

test('netease provider maps IDs, artists, album and fee', async () => {
  const fetcher = async () => Response.json({ result: { songs: [{ id: 123, name: 'A', artists: [{ name: 'B' }], album: { name: 'C' }, fee: 8 }] } });
  assert.deepEqual(await searchNetease('A', { fetcher }), [{ id: '123', name: 'A', artists: 'B', album: 'C', fee: 8 }]);
});

test('invalid responses and both provider failures return an empty list', async () => {
  const fetcher = async () => { throw new Error('synthetic timeout'); };
  assert.deepEqual(await searchSongs('A', { fetcher }), []);
  assert.deepEqual(await searchQQ('A', { fetcher: async () => ({ json: async () => { throw new SyntaxError('invalid JSON'); } }) }), []);
});

test('blank query makes no provider calls', async () => {
  let calls = 0;
  assert.deepEqual(await searchSongs('  ', { fetcher: async () => { calls++; } }), []);
  assert.equal(calls, 0);
});
