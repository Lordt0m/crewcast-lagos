// Presentation only. All forecast evaluation, freshness and permissions stay in Django.
type Scheduler = (
  callback: () => void,
  delay: number,
) => ReturnType<typeof setTimeout>;

export function createSequence(
  count: number,
  render: (active: number | null, complete: boolean) => void,
  announce: (text: string) => void,
  schedule: Scheduler = setTimeout,
  clear: (timer: ReturnType<typeof setTimeout>) => void = clearTimeout,
  now: () => number = Date.now,
) {
  let timers: ReturnType<typeof setTimeout>[] = [];
  let running = false;
  let lastStart = -Infinity;
  let generation = 0;
  function finish() {
    generation++;
    timers.forEach(clear);
    timers = [];
    running = false;
    render(null, true);
    announce("Sequence complete. All steps remain available.");
  }
  return {
    finish,
    play(immediate = false) {
      // A second activation settles the existing sequence, never restarts it.
      if (immediate || running || now() - lastStart < 1200) {
        finish();
        return;
      }
      lastStart = now();
      const current = ++generation;
      running = true;
      render(0, false);
      announce(
        "Following the steps. Activate replay again to show the complete explanation.",
      );
      for (let i = 1; i < count; i++) {
        timers.push(
          schedule(() => {
            if (current === generation) render(i, false);
          }, i * 650),
        );
      }
      timers.push(
        schedule(() => {
          if (current === generation) finish();
        }, count * 650),
      );
    },
  };
}

// One in-flight day request. An older response can never replace a newer choice.
export function createLatestRequest<T>(
  read: (url: string, signal: AbortSignal) => Promise<T>,
  commit: (value: T, url: string) => void,
  fail: (url: string) => void,
  busy: (value: boolean) => void,
) {
  let controller: AbortController | undefined;
  let generation = 0;
  const request = async (url: string) => {
    const current = ++generation;
    controller?.abort();
    controller = new AbortController();
    busy(true);
    try {
      const value = await read(url, controller.signal);
      if (current === generation) commit(value, url);
    } catch {
      if (current === generation) fail(url);
    } finally {
      if (current === generation) busy(false);
    }
  };
  return Object.assign(request, {
    cancel() {
      ++generation;
      controller?.abort();
      busy(false);
    },
  });
}

function enhanceDates(root: Document) {
  if (!root.querySelector('[data-planning-board]') ||
      !('fetch' in window) || !('AbortController' in window)) return;
  let keyboard = false;
  let push = true;
  const load = createLatestRequest<HTMLElement>(
    async (url, signal) => {
      const response = await fetch(url, {
        signal, credentials: 'same-origin', cache: 'no-store',
        headers: { 'X-CrewCast-Board': '1' },
      });
      if (!response.ok || response.redirected) throw new Error('Board unavailable');
      const html = new DOMParser().parseFromString(await response.text(), 'text/html');
      const next = html.querySelector<HTMLElement>('[data-planning-board]');
      if (!next) throw new Error('Board missing');
      return next;
    },
    (next, url) => {
      const board = root.querySelector<HTMLElement>('[data-planning-board]');
      if (!board) return;
      const picker = board.querySelector<HTMLElement>('.day-picker');
      const restoreDateFocus = keyboard && !!picker?.contains(root.activeElement);
      const top = picker?.getBoundingClientRect().top ?? board.getBoundingClientRect().top;
      const left = picker?.scrollLeft ?? 0;
      board.replaceWith(next);
      const nextPicker = next.querySelector<HTMLElement>('.day-picker');
      if (nextPicker) nextPicker.scrollLeft = left;
      // Preserve the date strip's position, even if the heading wraps differently.
      const delta = (nextPicker?.getBoundingClientRect().top ?? next.getBoundingClientRect().top) - top;
      if (delta) window.scrollBy({ top: delta, behavior: 'instant' });
      if (push) history.pushState({ crewcastBoard: true }, '', url);
      if (restoreDateFocus) next.querySelector<HTMLElement>('[aria-current="date"]')?.focus({ preventScroll: true });
    },
    (url) => {
      const status = root.querySelector<HTMLElement>('[data-board-status]');
      if (!status) return;
      status.textContent = 'That day could not load. Current jobs are unchanged. Select a date to retry, or ';
      const fallback = root.createElement('a');
      fallback.href = url;
      fallback.textContent = 'open the full day page';
      status.append(fallback, '.');
    },
    (value) => {
      const board = root.querySelector<HTMLElement>('[data-planning-board]');
      board?.toggleAttribute('data-loading', value);
      board?.setAttribute('aria-busy', String(value));
      const status = board?.querySelector<HTMLElement>('[data-board-status]');
      if (value && status) status.textContent = 'Loading selected day… Your current jobs remain visible.';
      if (!value && status?.textContent === 'Loading selected day… Your current jobs remain visible.') {
        status.textContent = `Showing ${board?.querySelector('.board-section-heading h2')?.textContent?.trim()}. Select a date to compare planned jobs.`;
      }
    },
  );
  root.addEventListener('click', (event) => {
    const link = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>('[data-board-date]') : null;
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (link.getAttribute('aria-current') === 'date') {
      load.cancel();
      return;
    }
    keyboard = event.detail === 0;
    push = true;
    void load(link.href);
  });
  window.addEventListener('popstate', () => {
    const board = root.querySelector('[data-planning-board]');
    if (!board) return;
    const selected = board.querySelector<HTMLAnchorElement>('[aria-current="date"]');
    const first = board.querySelector<HTMLAnchorElement>('[data-board-date]');
    const requestedDate = new URL(location.href).searchParams.get('date') || (first && new URL(first.href).searchParams.get('date'));
    if (selected && new URL(selected.href).searchParams.get('date') === requestedDate) {
      load.cancel();
      return;
    }
    keyboard = false;
    push = false;
    void load(location.href);
  });
}

export function enhance(root: Document = document) {
  enhanceDates(root);
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const finePointer = matchMedia("(hover: hover) and (pointer: fine)");
  const sequences: ReturnType<typeof createSequence>[] = [];
  const entrances: Animation[] = [];
  const stopMotion = () => {
    entrances.forEach((animation) => animation.cancel());
    sequences.forEach((sequence) => sequence.finish());
  };

  root.querySelectorAll<HTMLElement>("[data-sequence]").forEach((container) => {
    const beats = [
      ...container.querySelectorAll<HTMLElement>("[data-beat]"),
    ].sort(
      (a, b) => Number(a.dataset.order || 0) - Number(b.dataset.order || 0),
    );
    const button = container.querySelector<HTMLButtonElement>("[data-replay]");
    const status = container.querySelector<HTMLElement>(
      "[data-sequence-status]",
    );
    if (!button || !beats.length) return;
    beats.forEach((beat) => beat.classList.add("sequence-step"));
    const sequence = createSequence(
      beats.length,
      (active, complete) => {
        beats.forEach((beat, index) => {
          beat.toggleAttribute("data-active", index === active);
          beat.toggleAttribute(
            "data-complete",
            complete || (active !== null && index < active),
          );
        });
        container.toggleAttribute("data-playing", active !== null);
      },
      (text) => {
        if (status) status.textContent = text;
      },
    );
    button.hidden = false;
    button.addEventListener("click", (event) =>
      sequence.play(event.detail === 0 || reduced.matches),
    );
    sequences.push(sequence);
  });

  // Operational navigation and repeated date selections never replay the hero.
  let firstVisit =
    !!root.querySelector("[data-entrance]") &&
    !location.search &&
    !location.hash;
  try {
    firstVisit =
      firstVisit && sessionStorage.getItem("crewcast:introduced") !== "yes";
    if (firstVisit) sessionStorage.setItem("crewcast:introduced", "yes");
  } catch {
    /* The introduction works without browser storage. */
  }
  const connection = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
  const modestDevice = (navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 2) ||
    connection?.saveData || ['slow-2g', '2g', '3g'].includes(connection?.effectiveType || '');
  if (
    firstVisit &&
    !reduced.matches &&
    !modestDevice &&
    typeof Element.prototype.animate === "function"
  ) {
    root
      .querySelectorAll<HTMLElement>("[data-entrance] [data-enter]")
      .forEach((part, index) => {
        // Backwards fill coordinates delayed parts; failed enhancement leaves content intact.
        entrances.push(
          part.animate(
            [
              { opacity: 0.45, transform: "translateY(12px)" },
              { opacity: 1, transform: "translateY(0)" },
            ],
            {
              duration: 480,
              delay: index * 100,
              fill: "backwards",
              easing: "cubic-bezier(0.23, 1, 0.32, 1)",
            },
          ),
        );
      });
  }

  // Pointer feedback only; keyboard activation has no transform or delay.
  root.querySelectorAll<HTMLElement>(".btn").forEach((button) => {
    const release = () => {
      if (!button.hasAttribute("data-pressed")) return;
      button.removeAttribute("data-pressed");
      button.setAttribute("data-releasing", "");
    };
    button.addEventListener("pointerdown", (event) => {
      if (
        (button instanceof HTMLButtonElement && button.disabled) ||
        reduced.matches ||
        !finePointer.matches ||
        event.pointerType === "touch" ||
        event.button !== 0
      )
        return;
      button.removeAttribute("data-releasing");
      button.setAttribute("data-pressed", "");
    });
    button.addEventListener("pointerleave", release);
    button.addEventListener("pointercancel", release);
    button.addEventListener("blur", release);
    root.addEventListener("pointerup", release);
  });
  root.addEventListener("keydown", () => {
    root.documentElement.setAttribute("data-keyboard", "");
    stopMotion();
    root
      .querySelectorAll("[data-pressed],[data-releasing]")
      .forEach((button) => {
        button.removeAttribute("data-pressed");
        button.removeAttribute("data-releasing");
      });
  });
  root.addEventListener(
    "pointerdown",
    () => root.documentElement.removeAttribute("data-keyboard"),
    { capture: true },
  );
  root.addEventListener("visibilitychange", () => {
    if (root.hidden) stopMotion();
  });
  reduced.addEventListener("change", stopMotion);
  window.addEventListener("pagehide", stopMotion);
}

if (typeof document !== "undefined") enhance();
