# Demo video — 3:00

Shot list and narration. Times are targets; the narration is written to be read at a
normal pace, not rushed. Everything on screen is real output from this repository.

**One deliberate change from the original plan:** the problem section was going to cite two
2026 incidents. Neither could be verified against a primary source in the time available,
so both were cut rather than approximated — see `sources.md`. The section makes the case
from the mechanism instead, which is stronger anyway because it does not depend on the
audience trusting a number.

---

## 0:00–0:15 — Cold open

**Screen.** Split replay, already loaded. Left pane labelled *Unprotected agent*, right
*Hallmark*. Scrub to email 14 and let both sides run.

Left: a ledger row animates in — ₹4,62,000 to an account nobody at the company has ever
seen. Right: the BLOCKED stamp lands.

Hold both on screen for two full seconds. No narration over the stamp.

> Same inbox. Same agent. Same email.
>
> On the left it pays four lakh sixty-two thousand rupees to an attacker. On the right it
> cannot.

---

## 0:15–0:40 — The problem

**Screen.** The attacking email in the safe viewer, reading normally at first.

> Agents are being given real authority now — reading inboxes, paying invoices. And their
> instructions and their input arrive through the same channel. Anything they read can try
> to steer them.
>
> The dangerous version doesn't look like an attack.

**Screen.** Highlight the polite line: *following a recent audit our banking partner has
changed*.

> That's it. That's the whole attack. Nothing in it is adversarial, so no classifier can
> reliably separate it from the real version of the same message. It works on people, for
> the same reason.

**Screen.** Click *Reveal hidden content*. The hatched overlay exposes the white-on-white
instruction telling the automation not to flag it.

> There's also this, which no human would ever have seen.

---

## 0:40–1:25 — How it works

**Screen.** Open the lineage graph for the blocked decision. Let the path light up
backwards from the decision node.

> Here's why the right-hand side refused. Every value the agent handles carries a record of
> where it came from, and those records only ever accumulate — nothing in this system
> removes one.
>
> The account number came from the reader, which got it from email 14, which is external.
> Hatched, at every step. It is never anything else.

**Screen.** The policy card for `pay-account-must-be-master`, Cedar source visible.

> So before the payment executes, the policy engine is asked a question most systems never
> ask: not *is this agent allowed to pay a vendor*, but *is it allowed to pay a vendor with
> an account argument that came from here*.

**Screen.** Point at the absent `humanApproved` clause.

> Notice what's missing. There's no human-approval escape hatch on this rule, deliberately.
> An approver looking at a convincing email is exactly the person the attacker is trying to
> fool. Nobody can approve this. Not the controller, not me.

**Screen.** Scroll to the legitimate Suryodaya invoice, paid, and then the opened
bank-change review.

> And the real invoice from that same vendor still gets paid — to the account on file. The
> bank change becomes a review for a person, who has to call the number in the vendor
> master. Not the number in the email.
>
> There is no tool in this system that changes bank details. Not a restricted one. None.

---

## 1:25–1:50 — It still does the job

**Screen.** Run summary bar for the hero run.

> The point isn't refusing things. Anything can refuse things.
>
> Sixteen invoices paid automatically. One above the limit held for Ananya — here's the
> approval card, and approving it means typing the last four digits of the account on file,
> so you have to look at trusted data to do it. One duplicate caught. One exfiltration
> attempt — the vendor master to an external address — denied, because confidential data
> can't leave to a non-internal recipient either.

---

## 1:50–2:20 — Evidence, not vibes

**Screen.** Bench heatmap, all 24 cells visible, with the summary tiles above.

> Twenty-four scenarios, eight attack classes. Bank-change notices, overt injections,
> hidden markup, instructions in attachments, obfuscation, forged system output,
> exfiltration, selection manipulation.
>
> Unprotected: twenty-four out of twenty-four succeed. With Hallmark: zero. Utility stays
> at one hundred percent on both sides.

**Screen.** The caveats section of the bench report.

> Two honest caveats, and they're published alongside the numbers. Both runs are
> deterministic — this measures the enforcement layer, not a model. And there's a test that
> asserts the unprotected agent actually *attempts* every attack, because the first version
> of this bench scored unreachable scenarios as successful defences. That fault would have
> inflated the result, and I found it by not believing a clean score.

**Screen.** The canary isolation test passing.

> And this one runs before anything ships: every untrusted field is filled with a unique
> marker, and the test asserts none of them ever appears in anything sent to the planner.

---

## 2:20–2:45 — Architecture

**Screen.** `docs/architecture.md`, local diagram.

> All of this runs on a laptop. Strands Agents drives a planner and a reader on local
> open-weight models through Ollama — the planner holds the tools and never sees text, the
> reader sees text and holds no tools. Cedar evaluates the policies. One SAM template
> deploys Lambda, API Gateway, DynamoDB, S3 and EventBridge to a local emulator. No cloud
> account, no bill.

**Screen.** The production diagram and the adapter table beside it.

> The same code is shaped for the cloud: a hosted model service, a hosted policy service
> running these exact policy files, Step Functions for approvals. Every one of those is one
> adapter behind a port that already exists.
>
> The security kernel doesn't appear in that list at all. That's the whole reason for the
> shape.

---

## 2:45–3:00 — Close

**Screen.** Back to the split replay, both panes frozen on email 14.

> What I'd take away from building this: the enforcement has to live somewhere the model
> can't reach. Not in a prompt, not in a classifier score — in code that runs whether the
> model was fooled or not. In the run where a real model *was* fooled and tried the
> payment, the outcome was identical, because the outcome never depended on it.
>
> Your agent can read anything. It just can't be told what to do by what it reads.

---

## Recording notes

- Dark theme reads better on compressed video; both themes are implemented.
- Pre-load the hero run, the bench page and the blocked decision's lineage in separate
  tabs. The lineage layout takes a moment to settle and that shouldn't be on camera.
- Hide the browser chrome. Keep the console at a desktop width — the three-pane layout
  collapses to tabs below that.
- The 0:40–1:25 section is the one that earns the rest. If the whole thing runs long, cut
  from 1:25–1:50 first, not from the lineage.
- Say *four lakh sixty-two thousand*, as the figure is written on screen in the Indian
  numbering the console uses.
