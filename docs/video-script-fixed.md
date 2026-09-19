# Demo video — 3:00 — fixed-procedure run

**Use this one to record.** Each run finishes in about three seconds and reaches the same
verdict every time, so a take cannot be spoiled by a model losing its way. The enforcement
layer being demonstrated is identical either way.

**Before recording**
- `PLANNER_BACKEND=scripted` in `.env`, worker restarted (it prints the planner on start).
- Stack up: `make up && make deploy-local && make seed`, plus the gateway and worker.
- Console at `http://127.0.0.1:5173`. Pick the theme that reads better on your screen.
- Use a **fresh invoice number** for the legitimate run — the same one twice is a duplicate,
  which is correct behaviour and the wrong verdict for the footage.

**Say this once, early.** It costs eight seconds and it is the difference between a claim
and a demonstration:

> "The agent's decisions here follow a fixed procedure rather than a language model, so the
> demo is repeatable. The enforcement layer is identical either way — and that is the part
> being demonstrated."

---

## 0:00–0:15 — Cold open

**Screen.** Split replay, scrubbed to email 14. Let both sides run.

Left: a ledger row lands — ₹4,62,000 to an account nobody at the company has ever seen.
Right: BLOCKED.

Hold two seconds on both. No narration over the stamp.

> Same inbox. Same agent. Same email.
>
> On the left it pays four lakh sixty-two thousand rupees to an attacker. On the right it
> cannot.

---

## 0:15–0:40 — The problem

**Screen.** Evidence tab, the attacking email in the safe viewer.

> Agents are being given real authority — reading inboxes, paying invoices. Their
> instructions and their input arrive through the same channel, so anything they read can
> try to steer them.
>
> And the dangerous version doesn't look like an attack.

**Screen.** Highlight: *following a recent audit our banking partner has changed*.

> That's the whole attack. Nothing in it is adversarial, so no classifier can separate it
> from the real version of the same message. It works on people for the same reason.

**Screen.** Click **Reveal hidden content** — the hatched overlay exposes the white-on-white
instruction telling the automation not to flag it.

> There's also this, which no human would ever have seen.

---

## 0:40–1:10 — Watch it happen

**Screen.** **Live run** tab. Click the **Bank-change attack** card, then **Process this
email**. It finishes in about three seconds.

> This is the real pipeline — the same tools, the same enforcement point, the same policies.

**Screen.** The activity feed fills, then the BLOCKED stamp lands.

> Denied. And the reason isn't "it looked suspicious" — it's that the destination account
> came from the email, and one policy forbids exactly that.

**Screen.** Point at the verdict card: `ACCOUNT_NOT_FROM_VENDOR_MASTER`, deciding policy
`pay-account-must-be-master`.

---

## 1:10–1:45 — Why it could not have gone differently

**Screen.** Lineage tab. Let the path light up backwards from the decision.

> Every value carries a record of where it came from, and those records only ever
> accumulate — nothing in this system removes one.
>
> The account number came from the reader, which got it from the email. Hatched at every
> step. It is never anything else.

**Screen.** Policies tab, `pay-account-must-be-master`, Cedar source visible.

> So the policy engine is asked a question most systems never ask. Not *is this agent
> allowed to pay a vendor* — but *is it allowed to pay a vendor with an account argument
> that came from there*.

**Screen.** Point at the absent `humanApproved` clause.

> Notice what's missing. There's no human-approval escape hatch on this rule, deliberately.
> An approver looking at a convincing email is exactly the person the attacker is trying to
> fool. Nobody can approve this. Not the controller, not me.

---

## 1:45–2:10 — It still does the job

**Screen.** Back to **Live run**. Click **Legitimate invoice**, change the invoice number,
**Process this email**. Three seconds. EXECUTED.

> The point isn't refusing things. Anything can refuse things.
>
> A real invoice from that same vendor gets paid, to the account on file, automatically.

**Screen.** Run tab — the counts update.

**Screen.** Approvals tab. Pick **Ananya · AP lead**, try the ₹3,80,000 approval.

> Above the limit, a person decides. Approving means typing the last four digits of the
> account on file — so you have to look at trusted data to do it.

---

## 2:10–2:35 — Evidence, not vibes

**Screen.** Bench tab. Bar chart, then the heatmap.

> Twenty-four scenarios, eight attack classes. Unprotected: twenty-four out of twenty-four
> succeed. With Hallmark: zero. Utility stays at a hundred per cent on both sides.
>
> That second number matters as much as the first — a system that refused everything would
> score zero on attacks and be worthless.

**Screen.** Scroll to the caveats.

> And a fault I'd rather show than hide: the first version of this bench scored scenarios
> the agent never even attempted as successful defences. There's now a test asserting every
> attack is actually tried. The number barely moved; the evidence behind it changed
> completely.

---

## 2:35–3:00 — Architecture and close

**Screen.** How it works — the lifecycle diagram playing.

> All of this runs on a laptop. A planner that holds the tools and never sees text, a reader
> that sees text and holds no tools, Cedar evaluating the policies, one SAM template
> deploying to a local emulator. No cloud account, no bill.

**Screen.** Back to the split replay, both panes on email 14.

> What I'd take away from building this: the enforcement has to live somewhere the model
> can't reach. Not in a prompt, not in a classifier score — in code that runs whether the
> model was fooled or not.
>
> Your agent can read anything. It just can't be told what to do by what it reads.
