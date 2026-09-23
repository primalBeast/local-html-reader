import { hitsInText, type FindFlags, type TextHit } from './findMatch';

export type FindJob = {
  id: number;
  text: string;
  query: string;
  flags: FindFlags;
  from: number;
  to: number;
  sliceFrom: number;
};

self.onmessage = (event: MessageEvent<FindJob>) => {
  const job = event.data;
  const local = hitsInText(job.text, job.query, job.flags);
  const hits: TextHit[] = [];
  for (const hit of local) {
    const start = hit.start + job.sliceFrom;
    const end = hit.end + job.sliceFrom;
    if (start >= job.from && start < job.to) hits.push({ start, end });
  }
  self.postMessage({ id: job.id, hits });
};
