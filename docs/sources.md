# Sources and prior art

## Prior art this builds on

Hallmark is an engineering implementation of ideas that already exist. The contribution
here is putting them behind a policy engine that reasons about argument provenance, and
measuring the result — not the ideas themselves.

**The Dual LLM pattern** — Simon Willison, 2023.
<https://simonwillison.net/2023/Apr/25/dual-llm-pattern/>
The privileged/quarantined split: one model holds the tools and never sees untrusted
content, another reads untrusted content and holds no tools. Hallmark's planner and reader
are this pattern, with the addition that everything crossing between them is labelled.

**CaMeL — "Defeating Prompt Injections by Design"** — Debenedetti et al. (Google DeepMind
and ETH Zürich), 2025. <https://arxiv.org/abs/2503.18813>
Treats prompt injection as an information-flow problem rather than a detection problem, and
argues the control and data paths must be separated by construction. The direct ancestor of
the approach taken here.

**AgentDojo** — Debenedetti et al. (ETH Zürich), 2024.
<https://arxiv.org/abs/2406.13352>
A benchmark for agent robustness under attack, and the source of the discipline this
project's bench tries to follow: measure utility alongside attack success, because a system
that refuses everything trivially scores well on one and badly on the other.

**Information-flow control and taint tracking.** The label algebra here — sources that
join, confidentiality that takes the maximum, and no operation that removes a label — is
classic lattice-based IFC, as in Denning's work on secure information flow (1976) and the
decentralised label model of Myers and Liskov (1997).

**Cedar** — <https://www.cedarpolicy.com/>
The open-source policy language and engine. Policies are evaluated by `cedarpy`, the same
language a hosted policy service would use, which is why moving to one is an adapter change.

## Background on the problem

**Prompt injection**, named by Simon Willison in 2022 and still unsolved at the model
layer. <https://simonwillison.net/2022/Sep/12/prompt-injection/>
The framing that matters for this project: instructions and data share a channel, so no
amount of instruction-following training separates them reliably.

**Business email compromise.** The attack Hallmark's central scenario is modelled on. The
FBI's Internet Crime Complaint Center publishes annual figures on reported losses.
<https://www.ic3.gov/AnnualReport/Reports>

> **A note on numbers.** This project deliberately quotes no loss figure. The IC3 reports
> are the right primary source, and a figure should be read from the current one rather
> than repeated from memory or from a secondary article. Nothing in this repository depends
> on the size of that number — only on the mechanism, which is well documented and not in
> dispute.

## Tools and libraries

| | Role |
|---|---|
| [Cedar](https://www.cedarpolicy.com/) / `cedarpy` | Policy language and evaluation |
| [Strands Agents](https://github.com/strands-agents/sdk-python) | The agent loop and tool definitions |
| [Ollama](https://ollama.com/) | Local model serving |
| [Qwen3](https://github.com/QwenLM/Qwen3) | The open-weight models used for planner and reader |
| [LocalStack](https://localstack.cloud/) | Local AWS emulation |
| [AWS SAM](https://aws.amazon.com/serverless/sam/) | Infrastructure as code |
| [nh3](https://github.com/messense/nh3) / [ammonia](https://github.com/rust-ammonia/ammonia) | HTML sanitisation in the safe renderer |
| [Hypothesis](https://hypothesis.readthedocs.io/) | Property testing for the label algebra |

## On citation discipline

Every claim in the README and the bench report is either produced by a script in this
repository or attributed above. Where a figure would have made the case more dramatic but
could not be verified from a primary source in the time available, it was left out rather
than approximated.

The two incidents described in early drafts of this project's framing — a class of
zero-click agent-browser hijacks, and an agent-driven intrusion of a model host's
infrastructure — were removed for exactly this reason. They are the right kind of evidence,
but a security document should not assert incidents it has not sourced.
