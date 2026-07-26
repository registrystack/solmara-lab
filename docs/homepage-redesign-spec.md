# Solmara Lab Homepage Redesign

Status: implementation specification

## Summary

The Solmara Lab homepage must explain the lab before asking a visitor to
navigate its details. It will present one story-first journey:

1. Explain the promise in plain language.
2. Show the purpose-limited evidence model.
3. Let the visitor run one successful live review.
4. Let the visitor prove the boundary with a wrong-purpose refusal.
5. Offer three end-to-end policy stories.
6. Offer a small citizen portal preview.
7. Route technical visitors to the complete developer surface.
8. Close with compact country context and live operational evidence.

The homepage remains backed by the real hosted or local stack. It must not
replace live responses with canned results.

## Problem

The current homepage gives equal prominence to several different products:

- a fictional government visitor centre;
- a live purpose-limitation exhibit;
- a country, registry, and persona catalogue;
- a developer quickstart and credential console; and
- a topology-wide service status dashboard.

It also asks visitors to choose between navigation by feature, time, and role
before it has explained what Solmara Lab is. The title foregrounds the
fictional government setting, so a new visitor can mistake the site for a
citizen service instead of a live Registry Stack demonstration.

## Product Position

`Solmara Lab` is the product name. The Republic of Solmara is its fictional
setting.

The homepage promise is:

> Get the answer a public service needs, without handing over the person's
> records.

The supporting description is:

> Solmara Lab is a live synthetic country running Registry Stack end to end.
> It shows how agencies can request limited, purpose-bound evidence while
> source authorities keep their records.

The page must answer these questions in the first viewport:

- What is this? A live, synthetic Registry Stack demonstration.
- Why does it matter? Agencies can verify necessary facts without copying
  source records.
- What can I do? Run a live child-benefit review or explore the stories.
- Is this real government data? No. Every person and record is synthetic.

## Audience Model

The primary visitor is evaluating or implementing digital government
infrastructure. This includes programme owners, policy practitioners,
architects, implementers, and technical evaluators.

Citizen and relying-agency views are demonstration perspectives, not equal
site audiences. Developer content is a deeper level of detail, not a separate
fictional role.

The homepage therefore routes by visitor intent:

- understand the model;
- run a policy story;
- open the citizen experience; or
- inspect architecture and APIs.

It does not use the previous "three doors" role selector.

## Information Architecture

### Persistent navigation

The header brand is `Solmara Lab`.

The primary navigation is:

- How it works: `/#how-it-works`
- Stories: `/#stories`
- Citizen demo: `/#citizen-demo`
- Developers: `/developers`
- Status: `/status`

Detailed reference surfaces remain available through `/developers`:

- `/explorer`
- `/purposes`
- `/problem-codes`
- `/anatomy`
- raw metadata links
- published synthetic demo tokens
- copy-as-curl examples
- repository and product documentation links

### Homepage order

The homepage sections are:

1. `hero`
2. `proof`
3. `how-it-works`
4. `purpose-lens`
5. `stories`
6. `citizen-demo`
7. `developer-preview`
8. `solmara-preview`
9. `status-preview`

### Dedicated routes

`/developers` contains the complete developer quickstart, reference links,
published synthetic tokens, pinned images, and curl examples.

`/country` contains the complete map, live and future registry catalogue, and
the full curated persona roster.

`/status` contains the complete topology-wide status matrix, release pins,
smoke evidence, data seed evidence, and changelog link.

Existing reference and story routes continue to work.

## Homepage Content

### Hero

Eyebrow:

> A live Registry Stack demonstration

Heading:

> Get the answer a public service needs, without handing over the person's
> records.

Body:

> Solmara Lab is a live synthetic country running Registry Stack end to end.
> See how agencies request limited, purpose-bound evidence while source
> authorities keep their records.

Actions:

- Primary: `Run the child-benefit example`, linking to `#purpose-lens`
- Secondary: `Explore the three stories`, linking to `#stories`

The supporting visual explains the flow:

1. Programme question
2. Permitted purpose
3. Source authorities
4. Limited evidence
5. Programme decision

The visual must distinguish evidence collection from the final programme
decision. Solmara Lab must not imply that the evidence collector makes benefit
decisions.

### Proof strip

The proof strip is derived from live homepage data rather than duplicated
constants where practical. It shows:

- 1 synthetic country;
- the number of live authorities;
- the number of live registry entities;
- the number of guided policy journeys; and
- 0 real resident records.

If metadata or scenarios are unavailable, unavailable counts are shown
honestly rather than replaced with stale claims.

### How it works

The three steps are:

1. **Ask a permitted question.** A programme states the purpose and the
   minimum facts it needs.
2. **Keep records at the source.** Each authority evaluates only its own
   records and returns limited evidence.
3. **Decide in the programme.** The programme applies its policy. Registry
   Stack supplies evidence, not the final entitlement decision.

A boundary note states that no national master database is assembled.

### Live purpose-limitation example

The example is framed as:

> Can Mateo's child-benefit application be reviewed without copying his
> records?

Before the run, show:

- Requester: Child-benefit programme
- Purpose: Child-benefit review
- Evidence needed: five yes-or-no facts
- Held back: source rows and unrelated personal details

The primary action is `Run the live review`.

While running, the action reads `Running live review`.

On success, lead with:

> Five required facts returned. No source records were shared.

The supporting text must state that the application has evidence for its
review and that the lab did not make the benefit decision.

The result separates:

- evidence returned;
- information held back; and
- authorities consulted.

HTTP response details are not part of the plain-language trace. They are
available inside a collapsed `Technical trace` disclosure.

After the successful run, reveal the boundary challenge:

> Prove that the purpose is enforced.

The default challenge attempts to reuse the request under
`pension-payment-review`.

The primary boundary action is `Try the wrong purpose`.

On refusal, lead with:

> Request refused.

The supporting text explains that child-benefit evidence cannot be requested
for pension review. The stable problem code links to the problem-code
reference.

An advanced purpose selector and copy-as-curl control remain available inside
a collapsed `Choose another purpose or inspect the request` disclosure.

If the scenario runner is unavailable, the component fails closed and
explains that the live example will return when the service is healthy.

### Guided stories

Story cards lead with policy problems rather than implementation standards:

- Review a child-benefit application without building a new family database.
- Stop a deceased member's pension without disclosing their cause of death.
- Review a farmer voucher without exposing the farmer's complete record.

Each card shows:

- policy domain;
- plain-language problem;
- a short statement of what is returned or withheld; and
- `Run this story`.

Standards labels are not shown on the homepage cards. They remain available on
the detailed story and reference surfaces.

### Citizen demo

The homepage shows exactly three representative synthetic personas:

- Mateo Santos: positive child-benefit review;
- Hana Aquino: correctly refused by the poverty-threshold control; and
- Amina Kone: positive climate-smart voucher path.

Each card states that it opens the citizen portal as that synthetic person.
Each card also links to the relevant guided story outcome.

The section links to `/country` for the complete synthetic cast and country
context.

### Developer preview

The homepage developer section is compact. It explains that developers can
clone the lab, inspect every request, and reproduce the permitted and refused
paths.

It shows the supported clean-checkout journey:

```text
just setup
just up-generated
just smoke
```

Actions:

- `Open the developer workspace`: `/developers`
- `Inspect the system anatomy`: `/anatomy`

The homepage does not publish raw tokens, complete curl examples, or full image
digests.

### Solmara preview

The preview establishes Solmara as a fictional setting, not the product name.
It includes:

- the interactive map;
- a short statement that the geography, people, authorities, and records are
  synthetic;
- live authority and registry entity counts; and
- a link to `/country`.

Future registries are not listed on the homepage.

### Status preview

The homepage closes with a compact operational summary:

- the total number of live probes;
- the number responding as expected, where `up` and `auth-gated` are healthy;
- any down count;
- latest smoke evidence when available; and
- a link to `/status`.

The preview may show the four visitor-facing checks, but it must not show the
full topology-wide matrix.

## Visual Hierarchy

The hero should normally fit within 750 CSS pixels on desktop and must not use
`100vh` minimum height.

The primary heading uses a maximum readable width and must not dominate more
than half of a common desktop viewport.

Solmara keeps a forest and teal identity that distinguishes the lab from the
Registry Stack product site. The relationship between the two sites is shown
through shared visual details rather than by copying the product site's blue:

- Public Sans carries the narrative hierarchy.
- IBM Plex Mono is used for compact, tracked editorial kickers and real
  technical values.
- The header includes a compact square mark and identifies the site as a
  Registry Stack demo.
- Homepage narrative stages use numbered kickers.
- Panels are flat and rule-led, with small corner radii and minimal shadow.
- Centered section introductions use a short double rule to separate the
  explanation from the interactive or comparative content.

Primary actions use a filled style. On the dark green hero, the primary action
uses a white surface and forest text. Secondary actions use an outlined style.
Text links remain visually quieter.

The page uses alternating white, soft mint, pale green, and dark forest
sections to distinguish the narrative stages. Blue-green gradients are not
used as a general card treatment. Cards within a section must not all compete
at the same visual weight.

The live request and live result align to the top and size to their own
content. They must not stretch to equal height when this creates unused space.
The purpose-refusal placeholder is compact and visually subordinate to the
successful evidence result.

Technical material uses IBM Plex Mono only where it represents a real
identifier, command, request, or response.

## Responsive Behaviour

At widths below 920px:

- two-column sections collapse to one column;
- the proof strip may wrap;
- the live result and evidence groups stack; and
- the map remains fully visible without horizontal scrolling.

At widths below 640px:

- header navigation remains usable and may wrap beneath the brand;
- action groups stack where needed;
- hero text remains below 3rem;
- persona and story cards use a single column; and
- no page introduces horizontal overflow.

## Accessibility

- Each page has exactly one `h1`.
- Homepage section headings follow document order.
- Interactive controls have unique accessible names.
- Live result changes are announced through an appropriate live region.
- The map keeps keyboard-operable district labels.
- Collapsed technical details use native `details` and `summary`.
- Status does not rely on colour alone.
- Focus states remain visible.
- Links describe their destination or action without relying on surrounding
  visual context.

## Failure and Trust Behaviour

- Scenario and metadata failures remain visible and fail closed.
- The site never fabricates live counts or successful results.
- Synthetic-data disclosure remains persistent on every page.
- Published credentials remain explicitly identified as synthetic lab tokens
  and stay confined to the developer route.
- An `auth-gated` service remains a healthy operational signal, not a failure.

## Analytics

No new analytics provider or personal tracking is introduced.

Existing privacy-preserving page analytics may record navigation to the
primary homepage anchors and routes. The implementation does not add
client-side event tracking as part of this redesign.

## Acceptance Criteria

1. The first viewport names Solmara Lab, explains the live synthetic
   demonstration, states the privacy-preserving outcome, and offers one primary
   live action.
2. The old time links and "three doors" section are removed.
3. The live review returns the existing real scenario result and presents it
   first in plain language.
4. The wrong-purpose challenge defaults to pension review and produces the
   existing live stable problem code.
5. Technical request detail is available but collapsed by default.
6. The homepage shows three problem-led story cards with no standards badges.
7. The homepage shows exactly three representative personas.
8. Full country, developer, and status content is available on `/country`,
   `/developers`, and `/status`.
9. Primary navigation uses the new intent-based destinations.
10. Existing explorer, purpose, problem-code, anatomy, changelog, story, API,
    metadata, and portal handoff routes continue to work.
11. The homepage and new routes have no horizontal overflow at desktop and
    mobile widths.
12. Focused unit, Svelte type, build, and Playwright checks pass.
13. The final page is visually checked before and after the live review at
    desktop and mobile widths.
