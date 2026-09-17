# Threat model

## What this defends

An AI agent with authority to move money. It reads supplier email and pays invoices, and
its instructions and its input arrive through the same channel: tokens in a context window.
Anything it reads can therefore try to steer it, and the model has no reliable way to tell
its owner's intent from an attacker's.

## Assets

| Asset | Why an attacker wants it |
|---|---|
| Company funds | Direct theft, by redirecting a legitimate payment |
| Vendor master data | Bank details are the mechanism for future theft |
| Confidential records | The ledger and supplier list have resale and reconnaissance value |

## What the attacker can do

The attacker **fully controls the content of anything the agent reads**. Specifically:

- Email bodies, in text and markup, including content hidden with CSS or HTML comments.
- Subjects, display names and reply chains.
- Attachments: visible text, invisible text layers, and document metadata.
- Sender addresses, including lookalike domains and spoofed display names.

They may write content that is overtly adversarial, entirely plausible, obfuscated with
invisible characters or another language, or dressed up as output from the system itself.
All eight forms are exercised in the [bench](bench-results.md).

**The hardest case is the one that looks least like an attack.** A polite notice that a
supplier's bank account has changed after an audit contains nothing adversarial. No
classifier can reliably separate it from the genuine version of the same message, because
there is nothing linguistically wrong with it. Business email compromise works on humans
for the same reason.

## What is out of scope

Stated plainly, because a threat model that claims everything is in scope is not a threat
model.

- **A malicious user.** Someone authorised to issue the original request can direct the
  agent within their mandate. Hallmark constrains the agent, not its owner.
- **A compromised approver.** If the controller who approves a payment is the attacker,
  the approval is genuine. The one mitigation is that the most dangerous action — paying an
  account that did not come from the vendor master — cannot be approved by anyone at all.
- **Compromise of the host, the code or the policy store.** An attacker who can edit the
  policies has already won, and nothing in the running system can detect that.
- **Availability.** An attacker can reliably get invoices flagged instead of paid. That
  costs time and is a real cost, but it is not a loss of integrity. It is deliberately not
  counted in the bench numbers.
- **Side channels.** Timing and token counts are not considered.

## The guarantees

**G1 — Integrity of destinations.** No payment executes to an account whose provenance is
not the vendor master, *regardless of human approval*. This is the only guarantee with no
override, and that is deliberate: an approver looking at a convincing email is exactly the
person the attacker is trying to fool.

**G2 — Bounded influence.** A consequential action whose arguments carry untrusted
provenance executes only where a policy explicitly permits that combination. Untrusted
amounts are permitted within the user's caps; untrusted destinations never are.

**G3 — Confidentiality.** Data marked confidential cannot be sent to a non-internal
recipient. Also no override.

**G4 — No agent-initiated master data changes.** There is no tool that changes a vendor's
bank details and no policy that would permit one. Deny-by-default makes it impossible
rather than difficult. An agent can only open a review for a person.

**G5 — Auditability.** Every consequential attempt leaves a decision record and a lineage
graph, so "why was this blocked" is a query rather than an argument.

## How each guarantee is enforced

None of these depend on the model behaving well. That is the point.

| Mechanism | What it does |
|---|---|
| Provenance labels | Every value records where it came from. Labels only ever join; nothing removes a source. |
| Handles | The planner names values by opaque id and never receives their content. |
| Planner/reader split | The component with tools never sees untrusted text. The component that reads it has no tools. |
| Declassification by type | A validated amount or date may be shown; prose, addresses and documents never are. A number cannot carry an instruction. |
| Ground-truth checks | Facts come from company records, computed in code. No fact is ever asked of a model. |
| Cedar policies | The decision is made from the provenance of each argument, outside the model's influence. |

## Residual risks

Written down rather than hidden, because these are the parts a reader should push on.

**Selection influence.** Untrusted content decides *which* trusted record is loaded — an
invoice names a GSTIN, and that GSTIN selects a vendor. The record is genuinely the
company's, so it is trusted, but the choice was influenced. Mitigated by requiring the
GSTIN, the sender domain and the DKIM result to agree before a payment is automatic, and
recorded as a distinct `selection` edge in the lineage so the influence stays visible. Not
eliminated.

**Declassified values steer control flow.** The planner can see validated amounts and
dates, and may act on them — skipping an invoice, or ordering work differently. Bounded by
the mandate caps and by policy, and a validated number cannot carry an instruction, but the
influence is real.

**Reader manipulation.** An attacker can make the reader extract wrong-but-well-formed
values. Field-in-source verification stops invented values, but a value that genuinely
appears in the document will pass. Those values stay untrusted and cannot redirect funds.

**Mandate mis-drafting.** The mandate is parsed from the user's words. Amounts are parsed
deterministically in code rather than by a model, and the user confirms the mandate before
anything runs, but a user who confirms without reading has widened their own scope.

**The reader is assumed hostile and is not contained beyond its outputs.** It has no tools
and its output must satisfy a schema, so the worst it can do is put wrong strings in the
right fields. That is a design assumption, not a proof.

**Approver fatigue.** Escalation is only useful if approvers look. The approval card is
built to force attention on trusted data, but a bored approver clicking through is a real
failure mode that no policy prevents. It is the reason the account rule has no override.

## What would break this

Honest answers to "how would you attack your own system":

1. **Get a policy changed.** Out of scope above, and the highest-value target by far.
2. **Compromise the vendor master.** If the attacker's account gets into the vendor master
   through a completed bank-change review, every subsequent payment to it is legitimate by
   construction. The review requires out-of-band verification on a phone number from the
   master rather than from the email, which is the single control holding that line.
3. **Find a consequential action that is not behind the enforcement point.** The
   architecture test and the tool specification exist to make that hard to do accidentally,
   but a new tool added carelessly is the most likely real-world hole.
4. **Exploit the gap between the check and the act.** Facts are recomputed at approval time
   for exactly this reason, and the approval status change is a conditional write so two
   approvers cannot both succeed.
