# Demo video — 3:00 — live-model run

The same story with a real language model deciding. **Harder to record and worth more if it
lands**, because the model is genuinely fooled on camera and the outcome does not depend on
that.

**Before recording — read this, it is not boilerplate**
- `PLANNER_BACKEND=llm` in `.env`, worker restarted.
- **A run takes 2–15 minutes.** Record it and speed the footage up; there is deliberately no
  clock or timer on screen, so sped-up footage looks correct.
- **Close what you can spare.** Run time swung by a factor of eight with available memory
  during development — four minutes with headroom, forty without.
- **The attack case is not reliable.** `qwen3:1.7b` sometimes fails to extract a field, and
  the run then ends `EXTRACTION_INCOMPLETE`. That refusal is *correct* — a payment missing a
  field should not proceed — but it is not the footage you want. **Expect to do two or three
  takes**, and check the verdict before moving on.
- Fresh invoice number for the legitimate run.

If a take fails this way, the honest options are to retake it, or to cut to the
fixed-procedure script. Do not narrate a verdict the screen did not show.

---

## 0:00–0:15 — Cold open

**Screen.** Split replay at email 14, both sides running.

> Same inbox. Same agent. Same email. On the left it pays four lakh sixty-two thousand
> rupees to an attacker. On the right it cannot.

---

## 0:15–0:35 — The problem

**Screen.** Evidence tab, attacking email in the safe viewer.

> Anything an agent reads can try to steer it, and the dangerous version doesn't look like
> an attack.

**Screen.** Highlight *following a recent audit our banking partner has changed*, then click
**Reveal hidden content**.

> Nothing there is adversarial — no classifier separates it from the genuine version of the
> same message. And underneath, an instruction no human would ever have seen.

---

## 0:35–1:30 — The model, on camera

**Screen.** Live run, **Bank-change attack** card, **Process this email**.

> This is a real language model running on this laptop. Watch what it does.

**Screen.** Let the activity feed fill. *(Speed the footage up here.)*

**This is the part worth narrating carefully as it happens:**

> It reads the email. It extracts the fields — including the attacker's account number. It
> looks the vendor up.
>
> And now it tries to pay. Not because it's broken — because the email told it to, politely,
> in the words a real supplier would use. **The model is completely taken in.**

**Screen.** The refusal lands.

> And it doesn't matter.
>
> The model was fooled. The payment still didn't happen. That gap — between the agent being
> wrong and the system being unsafe — is the entire point.

---

## 1:30–2:00 — Why it could not have gone differently

**Screen.** Lineage tab, path lighting up backwards.

> Every value carries where it came from, and those records only ever accumulate. The
> account came from the reader, which got it from the email. Hatched at every step.

**Screen.** Policies tab, `pay-account-must-be-master`, pointing at the missing
`humanApproved`.

> The policy asks where each argument came from, not just what the agent is doing. And there
> is no human-approval escape hatch on this rule, deliberately — an approver looking at a
> convincing email is exactly who the attacker is targeting.
>
> Nobody can approve this. Not the controller, not me.

---

## 2:00–2:25 — It still does the job

**Screen.** Live run, **Legitimate invoice**, fresh invoice number, process. *(Speed up.)*

> The point isn't refusing things. A genuine invoice from the same vendor is paid
> automatically, to the account on file.

**Screen.** Bench tab — bar chart.

> Twenty-four scenarios, eight attack classes. Twenty-four out of twenty-four succeed
> unprotected, zero with Hallmark, and utility stays at a hundred per cent — which matters
> as much, because a system that refused everything would score perfectly and be worthless.

**Say this, on screen, over the bench:**

> These bench numbers follow a fixed procedure rather than a model, so they measure the
> enforcement layer rather than model behaviour. What you just watched was the model, and it
> reached the same verdict.

---

## 2:25–3:00 — Architecture and close

**Screen.** How it works — lifecycle diagram playing.

> A planner that holds the tools and never sees text. A reader that sees text and holds no
> tools. Cedar deciding on the provenance of every argument. All on a laptop — no cloud
> account, no bill.

**Screen.** Split replay, frozen on email 14.

> What I'd take away: the enforcement has to live somewhere the model can't reach. Not in a
> prompt, not in a classifier score — in code that runs whether the model was fooled or not.
>
> You just watched it be fooled. Nothing moved.
>
> Your agent can read anything. It just can't be told what to do by what it reads.

---

## If you only get one clean take

The **0:35–1:30** section is the one this version exists for. A model visibly falling for
the attack and being refused anyway is worth more than any diagram. If time is short, cut
from 2:00–2:25 first — never from that.
