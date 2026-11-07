import { beforeEach, describe, expect, it } from "vitest";
import { getDueReminder, resetReminderState, takeMissedEvents } from "../../src/core/reminders/reminderState";
import type { ReminderOut as Reminder } from "@smaran/contracts";

function makeReminder(hour: number, minute: number): Reminder {
  return {
    id: "r1",
    patient_id: "p1",
    category: "medicine",
    title: "Morning tablet",
    schedule: `FREQ=DAILY;BYHOUR=${hour};BYMINUTE=${minute}`,
    locale: "en",
    escalate_after_misses: 2,
    active: true
  };
}

beforeEach(() => resetReminderState());

describe("getDueReminder", () => {
  it("returns the reminder when now is within tolerance of its scheduled time", () => {
    const now = new Date();
    const reminder = makeReminder(now.getHours(), now.getMinutes());
    expect(getDueReminder([reminder], now)?.id).toBe("r1");
  });

  it("returns null when no reminder is close to its scheduled time", () => {
    const now = new Date();
    const farHour = (now.getHours() + 6) % 24;
    const reminder = makeReminder(farHour, 0);
    expect(getDueReminder([reminder], now)).toBeNull();
  });
});

describe("missed occurrences", () => {
  it("reports an unacknowledged occurrence once, after the grace period", () => {
    const due = new Date();
    due.setSeconds(30, 0);
    const reminder = makeReminder(due.getHours(), due.getMinutes());
    expect(getDueReminder([reminder], due)?.id).toBe("r1");
    expect(takeMissedEvents()).toHaveLength(0);
    const later = new Date(due.getTime() + 45 * 60_000); // grace is 30 min
    getDueReminder([reminder], later);
    const missed = takeMissedEvents();
    expect(missed).toHaveLength(1);
    expect(missed[0].reminder_id).toBe("r1");
    getDueReminder([reminder], new Date(later.getTime() + 60_000));
    expect(takeMissedEvents()).toHaveLength(0); // not reported twice
  });
});
