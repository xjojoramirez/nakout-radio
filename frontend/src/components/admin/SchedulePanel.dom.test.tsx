import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../../api/client";
import type { CurrentGenre, Genre, ScheduleSlot } from "../../types";
import { SchedulePanel } from "./SchedulePanel";

vi.mock("../../api/client", async () => {
  const actual =
    await vi.importActual<typeof import("../../api/client")>(
      "../../api/client",
    );
  return {
    ...actual,
    api: {
      ...actual.api,
      listSlots: vi.fn(),
      createSlot: vi.fn(),
      updateSlot: vi.fn(),
      deleteSlot: vi.fn(),
      scheduleNow: vi.fn(),
    },
  };
});

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

const genres: Genre[] = [
  {
    id: 1,
    name: "Emo Night",
    slug: "emo",
    is_default: false,
    color: "#f2a33a",
    track_count: 12,
  },
  {
    id: 2,
    name: "NU Metal",
    slug: "numetal",
    is_default: false,
    color: "#6fa3e0",
    track_count: 8,
  },
];

const slotsFixture = (): ScheduleSlot[] => [
  {
    id: 1,
    genre_id: 1,
    genre_name: "Emo Night",
    days_of_week: [0, 1, 2, 3, 4],
    start_time: "06:00",
  },
  {
    id: 2,
    genre_id: 2,
    genre_name: "NU Metal",
    days_of_week: [0],
    start_time: "09:30",
  },
];

const nowPayload = (): CurrentGenre => ({
  genre: genres[0],
  track: null,
  cursor: null,
  source: "schedule",
  offset_seconds: 0,
  server_time: "2026-10-09T04:00:00+00:00",
});

/** App weekday int (0 = Monday .. 6 = Sunday) from the browser's clock. */
function appToday(): number {
  return (new Date().getDay() + 6) % 7;
}

const SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const browserToday = new Date().getDay();

afterEach(() => {
  vi.clearAllMocks();
});

function renderPanel(
  overrides: Partial<Parameters<typeof SchedulePanel>[0]> = {},
) {
  const onNotice = overrides.onNotice ?? vi.fn();
  const onError = overrides.onError ?? vi.fn();
  const onCountChange = overrides.onCountChange ?? vi.fn();
  const onIntentConsumed = overrides.onIntentConsumed ?? vi.fn();
  render(
    <SchedulePanel
      genres={overrides.genres ?? genres}
      onNotice={onNotice}
      onError={onError}
      onCountChange={onCountChange}
      initialGenre={overrides.initialGenre}
      onIntentConsumed={onIntentConsumed}
    />,
  );
  return { onNotice, onError, onCountChange, onIntentConsumed };
}

async function openMonDay() {
  const group = screen.getByRole("group", { name: "Day of the week" });
  fireEvent.click(within(group).getByRole("button", { name: "Mon" }));
  await screen.findByRole("button", { name: /Emo Night/ });
  return group;
}

describe("SchedulePanel", () => {
  beforeEach(() => {
    mocked.listSlots.mockResolvedValue(slotsFixture());
    mocked.scheduleNow.mockResolvedValue(nowPayload());
  });

  it("shows the on-air card with the live genre", async () => {
    renderPanel();
    const big = await screen.findByText(/On air:/);
    expect(within(big).getByText("Emo Night")).toBeInTheDocument();
  });

  it("shows the nothing-scheduled on-air state when no genre is live", async () => {
    mocked.scheduleNow.mockResolvedValue({
      ...nowPayload(),
      genre: null,
      source: "none",
    });
    renderPanel();
    expect(await screen.findByText("Nothing scheduled yet")).toBeInTheDocument();
    expect(
      screen.getByText("Add a slot to start the automatic schedule."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/On air:/)).not.toBeInTheDocument();
  });

  it("orders day pills Sun-first with a today dot", async () => {
    renderPanel();
    await screen.findByText(/On air:/);
    const group = screen.getByRole("group", { name: "Day of the week" });
    const pills = within(group).getAllByRole("button");
    expect(pills).toHaveLength(7);
    expect(pills[0].textContent).toBe("Sun");
    expect(pills[1].textContent).toBe("Mon");
    expect(pills[6].textContent).toBe("Sat");
    const todayPill = pills.find((p) =>
      p.textContent?.startsWith(SHORT[browserToday]),
    );
    expect(todayPill?.querySelector(".tdot")).not.toBeNull();
    expect(
      within(group).getAllByRole("button", { pressed: true }),
    ).toHaveLength(1);
  });

  it("renders the timeline for the selected day and swaps with the pills", async () => {
    renderPanel();
    await screen.findByText(/On air:/);
    expect(screen.getByLabelText(/Timeline for /)).toBeInTheDocument();
    fireEvent.click(
      within(
        screen.getByRole("group", { name: "Day of the week" }),
      ).getByRole("button", { name: "Mon" }),
    );
    expect(
      await screen.findByLabelText("Timeline for Monday"),
    ).toBeInTheDocument();
    fireEvent.click(
      within(
        screen.getByRole("group", { name: "Day of the week" }),
      ).getByRole("button", { name: "Mon" }),
    );
    expect(
      await screen.findByRole("button", { name: /Emo Night/ }),
    ).toBeInTheDocument();
    expect(screen.getByText("9:30 AM")).toBeInTheDocument();
    fireEvent.click(
      within(
        screen.getByRole("group", { name: "Day of the week" }),
      ).getByRole("button", { name: "Sat" }),
    );
    expect(
      screen.queryByRole("button", { name: /Emo Night/ }),
    ).not.toBeInTheDocument();
  });

  it("clicking a timeline block opens the prefilled edit form", async () => {
    renderPanel();
    await openMonDay();
    fireEvent.click(screen.getByRole("button", { name: /Emo Night/ }));
    expect(await screen.findByText("Edit slot")).toBeInTheDocument();
    const form = screen.getByTestId("slot-form");
    const chip = within(form).getByRole("radio", { name: "Emo Night" });
    expect(chip).toHaveAttribute("aria-checked", "true");
    expect(within(form).getByLabelText("Start time")).toHaveValue("06:00");
    for (const day of ["Mon", "Tue", "Wed", "Thu", "Fri"]) {
      expect(within(form).getByRole("button", { name: day })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
    }
    expect(within(form).getByRole("button", { name: "Sat" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(within(form).getByRole("button", { name: "Sun" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(
      within(form).getByRole("button", { name: "Save slot" }),
    ).toBeEnabled();
  });

  it("opens the add form with sentence preview and gates save on the genre", async () => {
    mocked.listSlots.mockResolvedValue([]);
    renderPanel();
    await screen.findByText(/On air:/);
    fireEvent.click(screen.getByRole("button", { name: "+ Add slot" }));
    expect(await screen.findByText("Add a slot")).toBeInTheDocument();
    const form = screen.getByTestId("slot-form");
    expect(screen.getByTestId("sentence")).toHaveTextContent(
      "Pick a genre and a start time.",
    );
    const save = within(form).getByRole("button", { name: "Add slot" });
    expect(save).toBeDisabled();
    fireEvent.click(
      within(form).getByRole("button", { name: "Weekdays" }),
    );
    fireEvent.click(
      within(
        screen.getByRole("radiogroup", { name: "Genre" }),
      ).getByRole("radio", { name: "Emo Night" }),
    );
    expect(save).toBeEnabled();
    expect(screen.getByTestId("sentence")).toHaveTextContent(
      /Emo Night will start at 6:00 AM on weekdays and play until the next slot begins\./,
    );
  });

  it("day presets and pills set the repeated days", async () => {
    mocked.listSlots.mockResolvedValue([]);
    const { onNotice } = renderPanel();
    await screen.findByText(/On air:/);
    fireEvent.click(screen.getByRole("button", { name: "+ Add slot" }));
    const form = await screen.findByTestId("slot-form");
    fireEvent.click(
      within(form).getByRole("button", { name: "Weekends" }),
    );
    expect(within(form).getByRole("button", { name: "Sat" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(within(form).getByRole("button", { name: "Mon" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    fireEvent.click(within(form).getByRole("button", { name: "Mon" }));
    fireEvent.click(
      within(screen.getByRole("radiogroup", { name: "Genre" })).getByRole(
        "radio",
        { name: "NU Metal" },
      ),
    );
    fireEvent.click(within(form).getByRole("button", { name: "Add slot" }));
    await waitFor(() =>
      expect(mocked.createSlot).toHaveBeenCalledWith({
        genre_id: 2,
        days_of_week: [0, 5, 6],
        start_time: "06:00",
      }),
    );
    expect(onNotice).toHaveBeenCalledWith("Schedule slot added.");
    await waitFor(() =>
      expect(screen.queryByTestId("slot-form")).not.toBeInTheDocument(),
    );
    expect(mocked.listSlots).toHaveBeenCalledTimes(2);
  });

  it("a failed create surfaces the conflict inline instead of the toast", async () => {
    mocked.listSlots.mockResolvedValue([]);
    mocked.createSlot.mockRejectedValue(
      new ApiError(409, "a slot already starts at 06:00 on Mon"),
    );
    const { onNotice, onError } = renderPanel();
    await screen.findByText(/On air:/);
    fireEvent.click(screen.getByRole("button", { name: "+ Add slot" }));
    fireEvent.click(
      within(
        screen.getByRole("radiogroup", { name: "Genre" }),
      ).getByRole("radio", { name: "Emo Night" }),
    );
    fireEvent.click(
      within(screen.getByTestId("slot-form")).getByRole("button", {
        name: "Add slot",
      }),
    );
    const inline = await screen.findByText(/already starts at 06:00/);
    expect(inline.closest(".hint")).toHaveClass("err");
    expect(screen.getByTestId("slot-form")).toBeInTheDocument();
    expect(onNotice).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
  });

  it("saves an edit through updateSlot with the toggled days", async () => {
    mocked.updateSlot.mockResolvedValue({});
    renderPanel();
    await openMonDay();
    fireEvent.click(screen.getByRole("button", { name: /Emo Night/ }));
    const form = await screen.findByTestId("slot-form");
    fireEvent.change(within(form).getByLabelText("Start time"), {
      target: { value: "08:00" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Wed" }));
    fireEvent.click(within(form).getByRole("button", { name: "Save slot" }));
    await waitFor(() =>
      expect(mocked.updateSlot).toHaveBeenCalledWith(1, {
        genre_id: 1,
        days_of_week: [0, 1, 3, 4],
        start_time: "08:00",
      }),
    );
    await waitFor(() =>
      expect(screen.queryByTestId("slot-form")).not.toBeInTheDocument(),
    );
  });

  it("cancel closes the form", async () => {
    renderPanel();
    await openMonDay();
    fireEvent.click(screen.getByRole("button", { name: /Emo Night/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(screen.queryByTestId("slot-form")).not.toBeInTheDocument();
  });

  it("keeps the confirm dialog for deletion", async () => {
    mocked.deleteSlot.mockResolvedValue({ status: "deleted" });
    const { onNotice } = renderPanel();
    await openMonDay();
    const row = screen
      .getByText("6:00 AM to 9:30 AM")
      .closest(".srow") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(/Delete the Emo Night slot/),
    ).toBeInTheDocument();
    fireEvent.click(within(dialog).getByText("Delete"));
    await waitFor(() => expect(mocked.deleteSlot).toHaveBeenCalledWith(1));
    expect(onNotice).toHaveBeenCalledWith("Schedule slot deleted.");
    await waitFor(() => expect(mocked.listSlots).toHaveBeenCalledTimes(2));
  });

  it("lists the selected day with ranges, genre, duration chip and repeat label", async () => {
    renderPanel();
    await openMonDay();
    const first = screen
      .getByText("6:00 AM to 9:30 AM")
      .closest(".srow") as HTMLElement;
    expect(within(first).getByText("Emo Night")).toBeInTheDocument();
    expect(within(first).getByText("3h 30m")).toBeInTheDocument();
    expect(within(first).getByText("Weekdays")).toBeInTheDocument();
    const second = screen
      .getByText("9:30 AM to Midnight")
      .closest(".srow") as HTMLElement;
    expect(within(second).getByText("NU Metal")).toBeInTheDocument();
    expect(within(second).getByText("14h 30m")).toBeInTheDocument();
    expect(within(second).getByText("Mon")).toBeInTheDocument();
  });

  it("shows a dim carry row for the previous day's handover", async () => {
    renderPanel();
    await openMonDay();
    const carry = screen
      .getByText(/continues from Friday/)
      .closest(".srow") as HTMLElement;
    expect(carry).toHaveClass("dim");
    expect(carry.querySelector(".dot")).not.toBeNull();
    expect(carry.textContent).toContain("Midnight to 6:00 AM");
  });

  it("opens the add form at a gap row's minute", async () => {
    mocked.listSlots.mockResolvedValue([]);
    const { container } = render(<SchedulePanel
      genres={genres}
      onNotice={vi.fn()}
      onError={vi.fn()}
    />);
    await screen.findByText(/On air:/);
    fireEvent.click(
      within(
        screen.getByRole("group", { name: "Day of the week" }),
      ).getByRole("button", { name: "Mon" }),
    );
    const gapRow = container.querySelector(".srow.dim") as HTMLElement;
    expect(gapRow.textContent).toContain("Nothing scheduled");
    fireEvent.click(within(gapRow).getByRole("button", { name: "Add slot" }));
    expect(await screen.findByTestId("slot-form")).toBeInTheDocument();
    expect(screen.getByLabelText("Start time")).toHaveValue("00:00");
  });

  it("the empty-day button opens the form at 06:00 and the sentence says 6:00 AM", async () => {
    mocked.listSlots.mockResolvedValue([]);
    renderPanel();
    await screen.findByText(/On air:/);
    fireEvent.click(
      within(
        screen.getByRole("group", { name: "Day of the week" }),
      ).getByRole("button", { name: "Mon" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Add the first slot" }));
    expect(await screen.findByTestId("slot-form")).toBeInTheDocument();
    expect(screen.getByLabelText("Start time")).toHaveValue("06:00");
    fireEvent.click(
      within(
        screen.getByRole("radiogroup", { name: "Genre" }),
      ).getByRole("radio", { name: "Emo Night" }),
    );
    expect(screen.getByTestId("sentence")).toHaveTextContent(
      /will start at 6:00 AM/,
    );
  });

  it("prefills the genre from the initialGenre intent and consumes it once", async () => {
    const { onIntentConsumed } = renderPanel({ initialGenre: 2 });
    await screen.findByText(/On air:/);
    fireEvent.click(screen.getByRole("button", { name: "+ Add slot" }));
    const chip = within(
      screen.getByRole("radiogroup", { name: "Genre" }),
    ).getByRole("radio", { name: "NU Metal" });
    expect(chip).toHaveAttribute("aria-checked", "true");
    expect(onIntentConsumed).toHaveBeenCalledTimes(1);
  });

  it("reports the slot count after load and refreshes the on-air card", async () => {
    const { onCountChange } = renderPanel();
    await screen.findByText(/On air:/);
    await waitFor(() => expect(onCountChange).toHaveBeenCalledWith(2));
    await waitFor(() =>
      expect(mocked.scheduleNow.mock.calls.length).toBeGreaterThanOrEqual(2),
    );
  });

  it("resetting the day pill re-scopes an open add form's days", async () => {
    renderPanel();
    await screen.findByText(/On air:/);
    fireEvent.click(screen.getByRole("button", { name: "+ Add slot" }));
    const form = await screen.findByTestId("slot-form");
    fireEvent.click(within(form).getByRole("button", { name: "Weekends" }));
    fireEvent.click(
      within(
        screen.getByRole("group", { name: "Day of the week" }),
      ).getByRole("button", { name: "Mon" }),
    );
    expect(within(form).getByRole("button", { name: "Mon" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(within(form).getByRole("button", { name: "Sat" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("clicking the timeline strip opens the add form at the clicked minute", async () => {
    mocked.listSlots.mockResolvedValue([]);
    const { container } = render(
      <SchedulePanel genres={genres} onNotice={vi.fn()} onError={vi.fn()} />,
    );
    await screen.findByText(/On air:/);
    fireEvent.click(
      within(
        screen.getByRole("group", { name: "Day of the week" }),
      ).getByRole("button", { name: "Mon" }),
    );
    const tl = container.querySelector(".tl") as HTMLElement;
    Object.defineProperty(tl, "getBoundingClientRect", {
      value: () => ({
        left: 0,
        width: 1440,
        top: 0,
        right: 1440,
        bottom: 66,
        height: 66,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      }),
      configurable: true,
    });
    fireEvent.click(tl, { clientX: 361, clientY: 20 });
    expect(await screen.findByTestId("slot-form")).toBeInTheDocument();
    expect(screen.getByLabelText("Start time")).toHaveValue("06:00");
  });
});
