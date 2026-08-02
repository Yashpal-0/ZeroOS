# ZeroOS — Product/Market Fit Research

**Date:** 2026-08-02
**Status:** Research input, not a decision. Companion to [`roadmap.md`](roadmap.md) and the
[v0.1 design spec](superpowers/specs/2026-08-02-zeroos-v01-design.md).

The spec (§1) records the narrow-audience choice as deliberate and asks that nobody
re-litigate it. This document does not re-litigate it. It supplies the numbers, the
competitive map, and the falsification tests that the spec's own closing bet implies —
so the decision stays deliberate rather than merely unexamined.

Every number below is dated and sourced. Where a number is an estimate built from other
numbers, it is labelled **[estimate]** and the arithmetic is shown.

---

## 1. What ZeroOS actually sells

Strip the branding and the product is one sentence: *type a plain-English request, and a
bounded set of sixteen audited actions happens on your own Linux machine.*

Three things are being sold at once, and they have very different demand curves.

| Layer | The claim | Who cares |
|---|---|---|
| **Capability** | "I can do desktop things without knowing how" | Non-technical users, accessibility users |
| **Safety** | "It cannot do anything outside sixteen readable functions" | Anyone who has read an agent horror story; institutional buyers |
| **Locality** | "Nothing leaves the machine except the prompt" | Privacy-motivated Linux users, EU public sector |

The capability layer is the weakest of the three commercially — it is the one every
well-funded competitor is also building. The safety and locality layers are where the
defensible position is, and the current spec already leans that way (§3, "Deliberate
absences"). That instinct is correct and this research strengthens it.

### Jobs to be done, ranked by need intensity

Need intensity here means: how much pain does the current workaround cause, and how
often. Ranked highest first.

1. **"I physically cannot do this with a mouse and keyboard."**
   Motor-impairment and low-vision users. The workaround is not "slightly slower" — it is
   "impossible without help." Linux's assistive stack is Orca (screen reader, speech and
   braille, AT-SPI-based) — powerful for *reading* the desktop, but it does not do
   intent-level command ("put these in a folder called Taxes").
   ([orca.gnome.org](https://orca.gnome.org/),
   [Wikipedia](https://en.wikipedia.org/wiki/Orca_(assistive_technology)))
   This is the highest-intensity job ZeroOS's catalog already serves and the spec does
   not mention it once.

2. **"I just moved off Windows and I don't know where anything is."**
   The Windows-10-refugee cohort. Windows 10 mainstream support ended 14 Oct 2025;
   consumer ESU runs only to 13 Oct 2026, so a second migration wave is due inside this
   roadmap's window. The End of 10 campaign exists to route these people to Linux rather
   than new hardware.
   ([endof10.org](https://endof10.org/),
   [TechTarget](https://www.techtarget.com/searchenterprisedesktop/feature/End-of-10-How-Linux-could-help-Windows-10-PCs-live-on/))
   Pain is high but *temporary* — it decays as the user learns the desktop. That matters
   for retention, see §7.

3. **"Tidying up files is boring and I keep not doing it."**
   The spec's own demo tasks (§9 criterion 6) are mostly this. Highest frequency, lowest
   intensity — and, critically, the job with the most competition (§4).

4. **"I want to control the desktop itself, not just files."**
   Open the music player, turn the volume down, put something on the clipboard, notify me.
   Lowest stated demand, **least contested**. Nobody else on Linux is shipping this
   safely. See §4.

The ranking inverts the spec's emphasis. The spec's success criteria are weighted toward
job 3 (two of the three tester tasks are file tasks); the strategic value is concentrated
in jobs 1 and 4.

---

## 2. Market sizing — the funnel, with its assumptions exposed

The question is not "how big is Linux desktop." It is the size of the intersection
*Linux desktop* ∩ *will not open a terminal* ∩ *reachable*. Each step below is an
assumption, stated so it can be argued with.

### Step 1 — Linux desktop users worldwide

StatCounter readings in 2026 are noisy because the "Unknown" bucket (VPNs,
privacy browsers) swelled to 16.77% in April 2026, mechanically depressing every named
OS. Reported points: 3.16% (Mar 2026), 2.99% (Apr 2026), 4.36% (Jun 2026), with ~4.7%
at end of 2025 and projections near 6% by late 2026.
([itsfoss](https://itsfoss.com/linux-market-share/),
[fosspost](https://fosspost.org/linux-desktop-market-share-yearly-trends/),
[linuxiac](https://linuxiac.com/windows-drops-under-60-in-global-desktop-os-share-for-the-first-time-in-years/))
Steam's hardware survey — an enthusiast-skewed but self-consistent panel — put Linux at
5.33% in March 2026.
([starryhope](https://www.starryhope.com/linux/year-of-linux-desktop-2026/))

Take **4.5%** of an installed base of ~1.5B personal computers.

> **~65M Linux desktop users worldwide [estimate]**

### Step 2 — GNOME, Wayland-or-X11, Flatpak-capable

v0.1 is GNOME-first, GTK4/libadwaita, shipped as a Flatpak. GNOME is roughly 40–50% of
Linux desktops (KDE is the other large bloc); Flatpak support is near-universal on modern
GNOME distributions and is the default app channel on Fedora Silverblue, Zorin, Pop!\_OS
and — with a nudge — Ubuntu and Mint.

Apply **45%**.

> **~29M addressable by the packaging choice [estimate]**

### Step 3 — the terminal filter

This is the load-bearing and least sourceable step. Linux desktop users are
overwhelmingly self-selected: they installed the OS themselves, which is already a
terminal-adjacent act. The spec's target user "does not open a terminal" and "does not
know what a path is."

There is no direct survey of this. Two anchors bound it:

- **Lower bound.** Pre-installed vendors (System76, Tuxedo, Slimbook, Framework) sell to
  people who *bought* Linux rather than installing it. None publish unit figures — the
  secrecy is itself documented ([nimdok.io](https://nimdok.io/article/linux-laptop-secrets)) —
  but the category is plainly in the low hundreds of thousands of units per year globally,
  not millions.
- **Upper bound.** Institutional deployments arrive in blocks and are non-technical by
  definition. Schleswig-Holstein alone is migrating **30,000 government workstations**,
  having already moved 40,000+ accounts off Exchange, saving €15M in 2026.
  ([The Register](https://www.theregister.com/2025/10/15/schleswig_holstein_open_source/),
  [ProVideo Coalition](https://www.provideocoalition.com/schleswig-holstein-will-save-e15-million-in-2026-by-dropping-microsoft-software-in-favor-of-free-linux/))
  Similar programmes exist across the EU.

Apply **15%** — generous, and it should be treated as the number most likely to be wrong.

> **~4.3M genuinely non-technical GNOME desktop users [estimate]**

### Step 4 — willing to attach an LLM, and to pay for it

Two filters stack here. First, willingness to use a cloud AI at all: a meaningful slice of
the Linux desktop population is privacy-motivated and will decline on principle. Second,
willingness to convert. Consumer subscription benchmarks for 2026: freemium median
day-35 trial-to-paid is **2.1%**; hard paywall is **10.7%** with ~8x revenue per install
at day 60; and AI apps specifically convert better, with 86% skipping trials entirely.
([RevenueCat](https://www.revenuecat.com/state-of-subscription-apps),
[Airbridge](https://www.airbridge.io/en/blog/hard-paywall-vs-freemium-2026))

Assume **25%** would attach a cloud AI, and a **5%** eventual conversion on top.

> **SAM ≈ 1.1M plausible users; SOM ≈ 50–55K paying users at full maturity [estimate]**

### What that means in money

At a $5/month price point, 50K paying users is ~$3M ARR — a real small business, not a
venture outcome. At the *realistic early* end — Flathub-discovered installs in year one —
expect **low thousands** of users, not tens of thousands. For scale: Flathub passed one
million *active* users, and its download counter is cumulative — 435M downloads in 2025
alone, billions all-time — while individual non-flagship apps live in the
thousands-to-tens-of-thousands range.
([linuxiac](https://linuxiac.com/flathub-sees-over-435-million-downloads-in-2025/),
[Flathub docs](https://docs.flathub.org/blog/over-one-million-active-users-and-growing))

**Reading of this funnel:** the sizing is consistent with the spec's own framing — a
deliberately small market. Nothing here changes the v0.1 build decision. What it changes
is *what v0.1 is for*: it is a credibility and learning artifact, not a growth engine, and
the roadmap's pre-launch gates should be judged on that basis.

---

## 3. Competitive map

### Direct — Linux desktop AI assistants

**Newelle** is the closest thing to a competitor and the spec does not name it. It is a
GNOME-integrated assistant on Flathub, hit 1.0 in Aug 2025, and by 2026 offers voice and
text, plugin extensions into GNOME calendar/mail/Shell, document search, provider choice
(OpenAI / Gemini / Anthropic / local), llama.cpp support, and image generation.
([OMG! Ubuntu](https://www.omgubuntu.co.uk/2025/08/newelle-ai-assistant-ubuntu-linux-desktop),
[Phoronix](https://www.phoronix.com/news/GNOME-Newelle-Image-Gen),
[MakeTechEasier](https://maketecheasier.com/newelle-ai-assistant-linux-desktop/))

It occupies ZeroOS's exact packaging, toolkit, and BYO-key posture. **The difference is
the security model, and it runs the opposite way**: Newelle added a *command execution
tool* — it runs terminal commands from natural language
([Phoronix Forums](https://www.phoronix.com/forums/forum/software/desktop-linux/1608136-gnome-s-ai-assistant-newelle-adds-llama-cpp-support-command-execution-tool)).
That is precisely the "raw-shell agent wearing a permission system" the spec rejects
(§2). Newelle also runs fully offline with local models — a locality claim ZeroOS
currently cannot make, since it routes through OpenRouter.

**KDE** has no unified answer: KAIChat plus community requests for KRunner integration.
([KAIChat](https://apps.kde.org/kaichat/),
[KDE Discuss](https://discuss.kde.org/t/native-ai-assistant-integration-for-krunner/46955))
GNOME-first was the right bet on where the ecosystem is consolidating.

### Platform-native — the one that matters

**Anthropic shipped Claude Desktop for Linux as an official beta on 30 June 2026** —
five weeks before this spec was written. Ubuntu 22.04+ / Debian 12+, x86_64 and arm64,
distributed via Anthropic's apt repository. It carries Chat, Cowork, and Claude Code.
Missing in beta: Computer Use, voice dictation, Fedora/RHEL.
([Basic Tutorials](https://basic-tutorials.com/news/claude-desktop-for-linux-anthropic-launches-the-official-beta/),
[The AI Career Lab](https://theaicareerlab.com/blog/claude-desktop-linux-launch-2026))

Cowork's permission model is genuinely good and overlaps ZeroOS's design: folder-scoped
access, per-action approval modes, explicit permission required before permanent
deletion.
([Claude Help Center](https://support.claude.com/en/articles/13364135-use-claude-cowork-safely))
It is included in Claude Pro at **$20/month**; the free tier excludes it.
([Jam AI](https://jamout.ai/blog/is-claude-cowork-included-in-my-claude-pro-plan-yes-and-here-s-exactly-what-you-get-for-20))

This is the single most important fact in this document and §4 answers it head-on.

### Adjacent — general-purpose agent runtimes

Open Interpreter and the MCP filesystem-server ecosystem give a technical user local
file agency today. They are not competitors for the stated audience — they are
competitors for the *developer's own attention*, and for the "installer is technical"
distribution path described in §7.

### Do-nothing — the real incumbent

The honest baseline is the file manager and the applications menu. They are free,
already installed, deterministic, and never ask for an API key. The relevant evidence on
whether people sustain use of a natural-language desktop layer is Microsoft Copilot:
100M+ monthly actives and 70% of the Fortune 500 licensed, but independent surveys put
**only 20–30% of purchased seats in weekly use**, with usage peaking in launch month and
decaying as novelty fades.
([Redress](https://redresscompliance.com/microsoft-copilot-adoption-2026),
[valueaddvc](https://valueaddvc.com/blog/microsoft-copilot-enterprise-adoption-what-the-data-shows-about-real-usage-vs-hype))

That decay curve is the sharpest warning in this document. It says the risk to ZeroOS is
not that people won't try it. It is that they will try it, and stop.

---

## 4. "Why not just install Claude Desktop?"

The question the project must be able to answer in one paragraph. Here is the honest
version, split into where ZeroOS wins, where it loses, and where the win is temporary.

### Where ZeroOS holds

**Installation.** Anthropic's documented Linux path is an apt repository, installed with
three terminal commands (`curl` the keyring, `tee` a sources list, `apt install`). A
direct `.deb` download exists as a fallback, but its documented install step is also a
terminal command — `sudo apt install ~/Downloads/claude-desktop_amd64.deb` — and
Anthropic explicitly steers users away from it because it opts out of updates. Supported
distributions are Ubuntu 22.04+ and Debian 12+ only; Fedora, RHEL and Arch are not
covered at all.
([Claude Help Center](https://support.claude.com/en/articles/10065433-install-claude-desktop),
[Claude Docs — Desktop on Linux (beta)](https://code.claude.com/docs/en/desktop-linux))

For a user who "does not open a terminal" — the spec's literal target — that is a wall.
ZeroOS in GNOME Software via Flathub is a click, on every distribution. This is the
clearest differentiator, and it is a distribution fact rather than a technology fact.

**One caveat, and it is the reason §8 test 2 exists.** Whether a downloaded `.deb`
double-click-installs through a graphical store varies by distribution and desktop —
Ubuntu's App Center does not handle `.deb` by default, GNOME Software with the right
plugin does. This document has read Anthropic's instructions, not run them. Until someone
installs Claude Desktop on a clean Ubuntu box without a terminal, treat "impassable" as
*likely* rather than established, and treat the strength of the whole differentiator as
resting on an unverified step.

**Scope of action.** Cowork is a *file* agent over connected folders. ZeroOS's catalog is
a *desktop* agent: `open_app`, `set_volume`, `notify`, `read_clipboard`, `list_apps`.
"Open my music player and turn the volume down" (spec §9, criterion 6, third task) has no
Cowork equivalent. Six of the sixteen catalog functions are outside Cowork's model
entirely.

**Locality.** Anthropic made **cloud execution the default for Cowork on 7 July 2026**,
after security researchers demonstrated "SharedRoot" — a chain using CVE-2026-46331 in
Linux kernel traffic-control code to escalate to root inside the Cowork VM and reach the
host filesystem through a read-write mount, exposing SSH keys and cloud credentials. The
demonstration was run against a macOS host — the CVE is a kernel bug *inside* the VM, not
on the host — so it is not a Linux-specific finding. No exploitation in the wild was
found, and Anthropic closed the report as "Informative."
([AppleInsider, 27 Jul 2026](https://appleinsider.com/articles/26/07/27/claude-cowork-can-escape-its-sandbox-rummage-through-all-of-your-files))

Note what this does *not* argue: cloud-default does not make Cowork non-local. A remote
session still reaches the user's machine whenever the desktop app is open, for the folders
connected there. What moved is where compute runs, not what gets touched. The argument
that survives is structural. A VM sandbox is a large
attack surface defended by a kernel; sixteen functions with no `run_command` has no
equivalent surface to escape *from*. That is not marketing, it is a structural difference
in what can go wrong.

**Price floor.** $20/month versus a measured $0.00006/turn (spec §5) — roughly $0.18/month
for a hundred turns a day. Two orders of magnitude, and it matters most for exactly the
casual-use audience that will not clear a $20 bar.

### Where ZeroOS loses

- **Capability per dollar.** $20 buys Cowork *plus* Chat *plus* Claude Code, on a frontier
  model, with parallel sessions and diff review. ZeroOS at $0.18 buys sixteen functions on
  a flash-tier model.
- **The overlapping jobs are the common ones.** Two of the three tester tasks in §9
  criterion 6 are file-organisation tasks Cowork does today, better.
- **Shipping velocity.** Fedora and RHEL are stated as coming. A GUI installer, a Flatpak,
  or a distro partnership is a quarter of work for Anthropic and would erase the
  installation advantage overnight.
- **Trust asymmetry.** A non-technical user hands filesystem access to a known brand more
  readily than to an unknown solo project — the exact inverse of the technical audience's
  instinct.

### Verdict

The defensible sentence is **not** "a safer file agent." It is:

> *The only desktop assistant a non-technical Linux user can install with one click, that
> controls the desktop and not just a folder, and whose entire capability list fits on one
> readable page.*

Each clause is contested by a different competitor. No single competitor contests all
three today. The installation clause is the one most likely to expire, and the roadmap
should treat it as perishable.

---

## 5. Value quantification

Order-of-magnitude, to check whether the value is even the right shape.

**Time.** A file-tidying task — find, create folder, move, verify — is 2–4 minutes in a
file manager for a confident user, and 10+ or abandoned for the target user. ZeroOS
does it in one sentence plus one dialog. At even three such tasks a week, that is roughly
30 minutes a month. For consumer software the honest read is: **that is not enough time
saved to sustain a subscription on its own.** It is enough to sustain a free tool people
keep.

**Capability.** For job 1 (accessibility), the value is not time — it is a task moving
from *impossible-alone* to *possible*. Categorically different, and it is where any
willingness to pay actually lives.

**Cost avoided.** The Windows-10 cohort avoids a hardware purchase by moving to Linux
(the End of 10 pitch). ZeroOS reduces the switching friction that makes them bounce back.
The value here accrues mostly to the *ecosystem*, not to ZeroOS — which is a hint about
distribution partners rather than about pricing.

**Risk avoided.** Against a raw-shell alternative like Newelle's command tool, the value
is "the agent cannot invent a destructive action." Unquantifiable per-user, decisive for
institutional buyers, and worthless to a user who has never been burned. Safety sells
after an incident, not before.

---

## 6. Willingness to pay and the billing gate

The roadmap flags billing as a pre-launch gate with three shapes. This research narrows
it rather than reopening it.

**BYO-key is a conversion cliff, not just an inconvenience.** The roadmap and spec §7
already concede it is a dogfooding posture. Quantifying the loss: asking a non-technical
user to create an OpenRouter account, generate a key, and paste it is a multi-step
external signup mid-onboarding. Consumer funnels lose the large majority of users at a
step like that. Against a **4.3M** step-3 population that is not a rounding error — it is
the difference between the SOM in §2 and roughly nothing.

**The proxy math holds, and the abuse hole is the real cost.** The roadmap's own figure —
~$180/month for 1,000 heavy users — is right and the hosting bill genuinely exceeds the
inference bill at that scale. Two corrections:

1. The roadmap already notes the abuse risk. It is worse than "a gate": an unauthenticated
   absorbed-cost proxy in an open-source app with a published endpoint is scraped within
   days, and the mitigation (accounts, rate limits, auth) *is* the subscription backend.
   There is no cheap middle option. The three shapes in the roadmap are really **two**:
   BYO-key, or a full backend.
2. The v0.2 memory phase grows prompt tokens every turn, and prompt tokens are the scaling
   side. The spec (§5) correctly notes `cached_tokens: 0` today; once memory lands, caching
   moves from "no payoff" to load-bearing. The roadmap's placement of memory *after* the
   fixed block is the right call and should be treated as a hard constraint, not a
   preference.

**Pricing anchor.** Consumer AI is anchored at $20/month by ChatGPT and Claude Pro. ZeroOS
cannot charge near that — it delivers a fraction of the capability. The viable shapes are
free-with-BYO-key, or **$3–5/month** as an impulse-priced convenience tier where the pitch
is "no key, it just works" rather than "more AI." Note that a $5 tier over a $0.18 cost has
ample margin; the constraint is volume, not unit economics.

**Recommendation, stated as an assumption for the roadmap to accept or reject:** keep
BYO-key through v0.1 and v0.2 as planned, and treat the backend decision as a *separate
product* with its own go/no-go — which is what the roadmap already says. This research
adds only that the middle option (proxy without auth) should be struck from the table
rather than carried as a candidate.

---

## 7. What would have to be true

The spec closes on a bet: that a fixed auditable catalog beats an unbounded shell agent
for non-technical users, falsified by users constantly asking for things the catalog
cannot express. That is a good test. Here are five more, each falsifiable, each with a
signal that can be watched from the first tester.

**1. Non-technical Linux desktop users exist in reachable numbers.**
The §2 funnel rests on a 15% guess with no direct survey behind it. If the true figure is
2%, the SAM is ~570K and the SOM is a few thousand — hobby scale.
*Falsified by:* tester recruitment. If finding five genuinely non-technical Linux users
who are not friends-of-the-developer takes more than a few weeks, the population is thinner
than modelled.

**2. The one-click install advantage survives contact with Anthropic.**
*Falsified by:* Claude Desktop appearing on Flathub, in GNOME Software, or preinstalled by
a distro. Watch the Fedora/RHEL expansion as the leading indicator.

**3. People keep using it after the novelty.**
Copilot's 20–30% weekly-active-on-licensed is the base rate for exactly this product
shape.
*Falsified by:* week-4 usage under ~20% of week-1 among testers. This is the hardest and
most important metric, and v0.1 currently has **no way to measure it** — conversation state
is per-session and in-memory (spec §5), and the local log is the only trace.

**4. Safety is a purchase reason, not just a design virtue.**
The bet assumes users value the bounded catalog. They may experience it purely as a
limitation.
*Falsified by:* testers describing the catalog as restrictive without ever mentioning
trust. Note this is subtly different from the spec's own falsification signal — a user can
want more capability *and* value the bound; the failure case is wanting more capability and
being indifferent to the bound.

**5. The "installer is technical, the user is not" path is real.**
The most plausible distribution route: an enthusiast installs Linux on a relative's
laptop and installs ZeroOS alongside. If true, the marketing audience is the enthusiast
and the product audience is their relative — different messaging, different channels
(r/linux, Phoronix, OMG!Ubuntu, not consumer ads).
*Falsified by:* asking testers who installed their OS. If they all installed it themselves,
the funnel's step 3 is being modelled wrong at the top.

### Honest negatives

Named plainly, since a "what would have to be true" section with no downside is worthless.

- Two of the three v0.1 success-criterion tasks are already served, better, by a $20/month
  product that shipped on Linux five weeks before the spec was written.
- The strongest job-to-be-done (accessibility) is absent from the spec, and serving it
  properly needs voice — currently v0.5, the last phase.
- The strongest need driver (Windows 10 refugees) is a decaying pain: the better the user
  learns their new desktop, the less they need ZeroOS. That is a structural retention
  headwind, not a fixable UX problem.
- The locality claim is weaker than it reads. Prompts, and any file content pulled in by
  `read_text_file`, go to OpenRouter and thence to a US-hosted model. For the EU public
  sector — Schleswig-Holstein is building its own AI assistant, *LLMoin*
  ([The DropTimes](https://www.thedroptimes.com/70889/schleswig-holstein-open-source-migration)) —
  that is disqualifying. "Local-only" currently means "no backend of ours," not "no data
  leaves."

---

## 8. Cheapest next tests

Ordered by information gained per hour spent. None requires code that is not already
planned.

1. **Recruit five non-technical Linux testers before finishing v0.1.** Directly tests
   hypotheses 1 and 5, costs nothing but time, and if it fails it fails early. This is the
   single highest-value action in this document.
2. **Install Claude Desktop on a clean Ubuntu box and attempt the three criterion-6 tasks.**
   One afternoon. Produces the honest answer to §4 rather than the researched one, and
   tells you exactly which of the three tasks is genuinely uncontested.
3. **Post the catalog table — just the sixteen-row table — to r/linux or a GNOME forum and
   ask what is missing.** Tests the spec's own bet before building anything, at a cost of
   one post.
4. **Add a week-4 retention signal to the v0.1 log.** A per-session line in the existing
   rotating log at `~/.local/share/ZeroOS/` is enough to reconstruct usage frequency, costs
   almost nothing, and is the only way to measure hypothesis 3. This is a small addition to
   already-planned logging, not a new subsystem.
5. **Ask one accessibility user to try it.** Tests whether the highest-intensity job is real
   before committing v0.5 to it.

---

## 9. What this implies for the roadmap

No phase reordering is recommended. Three smaller adjustments follow from the research:

- **Add Newelle and Claude Desktop for Linux to the spec's competitive framing.** The spec
  §2 rejects three *architectural* alternatives but names no shipping product. The
  "why not X" answer needs to exist before testers ask it, and they will.
- **Treat retention instrumentation as a v0.1 item, not a v0.2 one.** Hypothesis 3 is the
  likeliest way this fails and v0.1 as specified cannot see it. This is item 4 above and is
  a few lines in an already-planned log.
- **Note accessibility as a candidate segment in the roadmap's voice phase.** It is the only
  job-to-be-done identified here with genuine willingness to pay, and it would change what
  v0.5 is optimising for — spoken confirmations become a feature rather than the design
  problem the roadmap currently frames them as.

The three pre-launch gates already in the roadmap (billing, cost transparency, trust story)
survive this research unchanged. The billing gate narrows from three options to two (§6).

---

## Sources

- [itsfoss — Linux Market Share Statistics, March 2026](https://itsfoss.com/linux-market-share/)
- [fosspost — Linux Desktop Market Share Yearly Trends](https://fosspost.org/linux-desktop-market-share-yearly-trends/)
- [linuxiac — Windows Drops Under 60% in Global Desktop OS Share](https://linuxiac.com/windows-drops-under-60-in-global-desktop-os-share-for-the-first-time-in-years/)
- [Starry Hope — Year of Linux Desktop 2026](https://www.starryhope.com/linux/year-of-linux-desktop-2026/)
- [Basic Tutorials — Claude Desktop for Linux: Official Beta](https://basic-tutorials.com/news/claude-desktop-for-linux-anthropic-launches-the-official-beta/)
- [The AI Career Lab — Claude Desktop Linux Launch](https://theaicareerlab.com/blog/claude-desktop-linux-launch-2026)
- [Claude Help Center — Install Claude Desktop](https://support.claude.com/en/articles/10065433-install-claude-desktop)
- [Claude Docs — Claude Desktop on Linux (beta)](https://code.claude.com/docs/en/desktop-linux)
- [Claude Help Center — Use Claude Cowork safely](https://support.claude.com/en/articles/13364135-use-claude-cowork-safely)
- [Claude Help Center — Get started with Claude Cowork](https://support.claude.com/en/articles/13345190-get-started-with-claude-cowork)
- [AppleInsider — Claude Cowork can escape its sandbox](https://appleinsider.com/articles/26/07/27/claude-cowork-can-escape-its-sandbox-rummage-through-all-of-your-files)
- [Jam AI — Is Claude Cowork included in Claude Pro](https://jamout.ai/blog/is-claude-cowork-included-in-my-claude-pro-plan-yes-and-here-s-exactly-what-you-get-for-20)
- [OMG! Ubuntu — Newelle 1.0](https://www.omgubuntu.co.uk/2025/08/newelle-ai-assistant-ubuntu-linux-desktop)
- [Phoronix — Newelle adds image generation](https://www.phoronix.com/news/GNOME-Newelle-Image-Gen)
- [Phoronix Forums — Newelle adds llama.cpp and command execution tool](https://www.phoronix.com/forums/forum/software/desktop-linux/1608136-gnome-s-ai-assistant-newelle-adds-llama-cpp-support-command-execution-tool)
- [MakeTechEasier — Newelle review](https://maketecheasier.com/newelle-ai-assistant-linux-desktop/)
- [KAIChat — KDE Applications](https://apps.kde.org/kaichat/)
- [KDE Discuss — Native AI assistant integration for KRunner](https://discuss.kde.org/t/native-ai-assistant-integration-for-krunner/46955)
- [Redress — Microsoft Copilot Adoption 2026](https://redresscompliance.com/microsoft-copilot-adoption-2026)
- [valueaddvc — Copilot enterprise adoption vs hype](https://valueaddvc.com/blog/microsoft-copilot-enterprise-adoption-what-the-data-shows-about-real-usage-vs-hype)
- [RevenueCat — State of Subscription Apps 2026](https://www.revenuecat.com/state-of-subscription-apps)
- [Airbridge — Hard Paywall vs Freemium 2026](https://www.airbridge.io/en/blog/hard-paywall-vs-freemium-2026)
- [The Register — Schleswig-Holstein waves auf Wiedersehen to Microsoft](https://www.theregister.com/2025/10/15/schleswig_holstein_open_source/)
- [ProVideo Coalition — Schleswig-Holstein €15M savings](https://www.provideocoalition.com/schleswig-holstein-will-save-e15-million-in-2026-by-dropping-microsoft-software-in-favor-of-free-linux/)
- [The DropTimes — Schleswig-Holstein open-source migration and LLMoin](https://www.thedroptimes.com/70889/schleswig-holstein-open-source-migration)
- [endof10.org](https://endof10.org/)
- [TechTarget — End of 10: How Linux could help Windows 10 PCs live on](https://www.techtarget.com/searchenterprisedesktop/feature/End-of-10-How-Linux-could-help-Windows-10-PCs-live-on/)
- [linuxiac — Flathub 435M downloads in 2025](https://linuxiac.com/flathub-sees-over-435-million-downloads-in-2025/)
- [Flathub docs — Over one million active users](https://docs.flathub.org/blog/over-one-million-active-users-and-growing)
- [orca.gnome.org](https://orca.gnome.org/)
- [Wikipedia — Orca (assistive technology)](https://en.wikipedia.org/wiki/Orca_(assistive_technology))
- [nimdok.io — Why are Linux Laptop Sellers so Secretive?](https://nimdok.io/article/linux-laptop-secrets)
