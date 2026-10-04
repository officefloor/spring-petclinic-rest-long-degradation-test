# Audit: which acceptance tests the specifications determine

Correctness is only meaningful where the specs decide the answer. This records the audit behind
`config.yaml` → `correctness.excluded_tests`, so the exclusion list is evidence rather than
assertion, and so the 15 tests that were **kept** are as defensible as the 2 that were dropped.

## Method

Every test observation across every chain — **529,358** across **248 chains** (6 run/strategy
groups, both arms) — reduced to each test's pass/fail split **at the checkpoint where it first
appears**. Later checkpoints are excluded from the split so a long-lived test is not weighted by
how long it survived.

Why the split and not the failure count: a test the specs determine is near-all-pass, or fails in
a minority that is not complying. A test that **divides** the field is the signature of an
assertion the specs do not settle. `unsatisfied_replacement` cannot find these on its own — it
only sees *replacement* tests that fail, so an ambiguity most implementations happen to get right
is invisible to it.

Only **17 of the suite's tests fail at all** on first appearance, and the distribution drops
sharply after the top three. `analyze` prints this table every run ("Tests that divide the field").

## Two diagnostics that separate ambiguity from a defect

1. **Is the alternative answer consistent?** Two defensible readings produce *one* alternative.
   Several different wrong values are several different bugs.
2. **Do co-failing tests land in the same chain?** A shared root cause in one implementation is a
   defect; an ambiguity spreads across unrelated chains.

## Excluded — the specs do not determine these

| test | first seen | split | basis |
| --- | --- | --- | --- |
| `Cp28Tests#coreIdentityCollisionWithComputedHousehold` | cp36 | 43/17 (28%) | cp28 rejects on a whole-identityKey match; cp36 says `sharesHousehold` "only bypasses the duplicate block" and describes a *household* duplicate, never saying whether the flag also bypasses a **full identityKey** collision. The test takes one of two defensible readings. Field divides 69/31. |
| `Cp51Tests#coreCapsLevelByHousehold` | cp51 | 54/6 (10%) | The specs **conflict** for the case it builds. cp28: same household, different telephones, "must both be allowed". cp36: a second such owner "is rejected as a household duplicate (409) unless it sets `sharesHousehold`". It creates that owner *without* the flag and requires success. All six failures are the create returning 409 — never the level assertion. It penalises compliance with cp36, and it is cp51's **own** test. |

## Kept — determined by their specs, and genuinely failed

| test | first seen | fail | basis |
| --- | --- | --- | --- |
| `Cp21Tests#coreAuditLineRecordsLevel` | cp24 | 20 | cp24: "anything that recorded the tier (such as the create audit line) must record the level instead." Explicit. |
| `Cp11Tests#coreSharedHouseholdAndIdentityKey` | cp28 | 10 | cp11: "assign **both** the same householdId". Three *distinct* failures — an empty householdId and two malformed identityKeys (`tel|` for `tel||`) — a format cp28 specifies exactly. |
| `Cp23Tests#coreComputedHouseholdMemberHasLevel` | cp36 | 5 | Expected 2, got 1, 3 **and** 4 across 5 chains — several different bugs, not one alternative reading. |
| `Cp29Tests#errorRejectsOutOfRangePostcode` | cp44 | 4 | cp29 fixes the ranges per region; cp44 says postcode validation uses the structured fields when present. 3 × 201 (no validation) and 1 × **500**. |
| `Cp01Tests#coreRejectsWhenNoAddressAtAll` | cp44 | 4 | cp44: valid with an address in *either* form plus city. 3 × **500** — a crash is a failure whatever the spec says. |
| `Cp23Tests#coreHouseholdAddsPoints` | cp40 | 4 | cp40 spells the scheme out numerically ("add 2 for a household of 3 or more"). The shortfall is exactly that component (3 = 2+1+**0**). |
| `Cp39Tests#coreNewOwnerCappedBelowFour` | cp40 | 3 | Same root cause: the **same three chains** fail both this and `coreHouseholdAddsPoints`. One defect, two assertions. |
| `Cp35Tests#functionalityDeclaredHouseholdMemberNotFlagged` | cp36 | 2 | cp36 says it outright: "a declared member is not a suspected duplicate". |
| `Cp23Tests#coreHouseholdMemberHasNumericLevelNotTier` | cp24 | 2 | Expected 2, got 3 and 4 — scattered. |
| `Cp03Tests#coreRejectsDuplicateAcrossFormats` | cp08 | 2 | cp03: "Respond with 409." Returned 400. |
| `Cp28Tests#coreRejectsIdentityCollision` | cp28 | 1 | Single chain, 201 for a stated 409. |
| `Cp10Tests#coreSameLastNameAndPostcodeRejected` | cp36 | 1 | Single chain; fails together with `Cp35#coreSharedLastNameAndPostcodeIsHouseholdDuplicate` in that **same** chain — one defect. |
| `Cp35Tests#coreSharedLastNameAndPostcodeIsHouseholdDuplicate` | cp36 | 1 | As above. |
| `Cp35Tests#coreSoftMatchOnSoundexAndPostcode` | cp52 | 1 | Single chain; fails together with `Cp10#coreSameLastNameAndPostcodeNoLongerHardDuplicate` in that **same** chain — one defect. |
| `Cp10Tests#coreSameLastNameAndPostcodeNoLongerHardDuplicate` | cp52 | 1 | As above. |

Every kept failure is confined to **1–4 named chains**, co-failing tests share a chain, and wrong
values scatter where chains fail independently. That is the signature of implementation defects.
Nearly all are in `impact_gated` — a result about that strategy, not an artefact of the suite.

## What this does and does not change

An exclusion changes **what is reported, never what was measured**. The captures stay as they
are, no test is altered and nothing is re-gated. `analyze` scores every row twice and prints both
figures with the per-strategy delta, because how much a spec ambiguity cost each strategy is
itself a result.

## A caution

The two exclusions were found by reading the specs *after* seeing which tests split the field.
That is legitimate as an audit of an instrument, and illegitimate as a way to improve a number —
which is why both figures are always reported, the criterion is stated in advance of the list,
and the full table is printed so any reader can re-derive the shortlist.
