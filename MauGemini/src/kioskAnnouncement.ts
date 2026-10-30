import type { Receipt } from './kioskFlow';

// Remember server event IDs across reloads: recovery is not a new attendance.
export class KioskAnnouncement {
  private seen: Set<string>;
  private remember: (ids: string[]) => void;
  constructor(ids: string[], remember: (ids: string[]) => void) {
    this.seen = new Set(ids.slice(-100)); this.remember = remember;
  }
  async announce(receipt: Receipt, play: () => Promise<void>) {
    if (receipt.status !== 'recorded' || this.seen.has(receipt.event_id)) return;
    this.seen.add(receipt.event_id);
    this.seen = new Set([...this.seen].slice(-100));
    this.remember([...this.seen]);
    await play();
  }
}
