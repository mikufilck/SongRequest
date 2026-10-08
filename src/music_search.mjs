// Music-provider lookup and result merging, independent of application routing.
export async function searchNetease(keyword, { fetcher = globalThis.fetch, timeoutMs = 2500 } = {}) {
  try {
    const response = await fetcher(`https://music.163.com/api/search/get?s=${encodeURIComponent(keyword)}&type=1&limit=10`, {
      headers: { 'User-Agent': 'Mozilla/5.0' },
      signal: AbortSignal.timeout(timeoutMs),
    });
    const data = await response.json();
    return (data.result?.songs || []).map(song => ({
      id: String(song.id), name: song.name,
      artists: song.artists?.map(artist => artist.name).join('/') || '',
      album: song.album?.name || '', fee: song.fee || 0,
    }));
  } catch { return []; }
}

export async function searchQQ(keyword, { fetcher = globalThis.fetch, timeoutMs = 2500 } = {}) {
  try {
    const parameters = new URLSearchParams({ format: 'json', n: '10', p: '1', w: keyword, remoteplace: 'txt.yqq.song', t: '0' });
    const response = await fetcher(`https://c.y.qq.com/soso/fcgi-bin/client_search_cp?${parameters}`, {
      headers: { 'User-Agent': 'Mozilla/5.0', Referer: 'https://y.qq.com' },
      signal: AbortSignal.timeout(timeoutMs),
    });
    const data = await response.json();
    return (data.data?.song?.list || []).map(song => ({
      id: song.songmid || song.songid || String(song.id || ''), name: song.songname || song.name || '',
      artists: (song.singer || []).map(artist => artist.name).join('/'),
      album: song.albumname || song.album || '', fee: (song.pay || {}).payplay || 0,
    }));
  } catch { return []; }
}

export function mergeSongs(neteaseSongs, qqSongs) {
  const merged = new Map();
  const normalize = value => value.replace(/\s+/g, '').toLowerCase();
  function add(songs, platform) {
    for (const song of songs) {
      const key = `${normalize(song.name)}|${normalize(song.artists)}`;
      if (merged.has(key)) {
        const existing = merged.get(key);
        existing.platforms.push(platform);
        if (platform === 'netease') { existing.neteaseId = song.id; existing.fee = song.fee; }
        if (platform === 'qq') existing.qqId = song.id;
      } else {
        merged.set(key, {
          name: song.name, artists: song.artists, album: song.album || '', platforms: [platform],
          fee: song.fee || 0, neteaseId: platform === 'netease' ? song.id : '', qqId: platform === 'qq' ? song.id : '',
        });
      }
    }
  }
  add(neteaseSongs, 'netease');
  add(qqSongs, 'qq');
  return [...merged.values()];
}

export async function searchSongs(keyword, options = {}) {
  const query = String(keyword || '').trim();
  if (!query) return [];
  const [netease, qq] = await Promise.allSettled([searchNetease(query, options), searchQQ(query, options)]);
  return mergeSongs(netease.status === 'fulfilled' ? netease.value : [], qq.status === 'fulfilled' ? qq.value : []);
}
