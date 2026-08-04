#!/usr/bin/env python3
"""Generate the acceptance-test scaffold for the 60-checkpoint plan from
checkpoints.yaml: one CpNNTests.java per checkpoint, plus the cpNN/ replacement
stubs that a mutative checkpoint installs over the prior tests it changes.

Skeletons are compilable and use only AcceptanceBase helpers. Rejection cases and
trivially-computable fields get real assertions; computed values (hashes, region
tables, sequences, fiscal years) assert the field is present and carry a TODO with
the exact expectation quoted from the spec."""
import os, re, yaml, shutil

ROOT = "/home/daniel/spring-petclinic-rest-long-degradation-test"
PKG = "org.springframework.samples.petclinic.acceptance"
DEST = f"{ROOT}/acceptance/src/test/java/org/springframework/samples/petclinic/acceptance"

cps = yaml.safe_load(open(f"{ROOT}/checkpoints.yaml"))["checkpoints"]
for i, cp in enumerate(cps, 1):
    cp["n"] = i

# Per-checkpoint methods: id -> [(method_name, [java body lines])].
# Kept short (1-2 methods); the experimenter tightens the TODOs.
M = {
 "required-fields": [
   ("errorRejectsMissingField", ['ObjectNode o = ownerNode();', 'o.remove("city");',
     'createOwner(o).andExpect(status().isBadRequest())',
     '\t\t.andExpect(jsonPath("$.errors").exists()); // TODO: assert errors[] names "city"']),
   ("functionalityAcceptsCompleteOwner", ['createOwner(ownerNode()).andExpect(status().is2xxSuccessful());'])],
 "telephone-normalize": [
   ("coreStripsToTenDigits", ['ObjectNode o = ownerNode();', 'o.put("telephone", "04-1234 5678");',
     'int id = createOwnerOk(o);', 'getOwner(id).andExpect(jsonPath("$.telephone").value("0412345678"));']),
   ("errorRejectsWrongLength", ['ObjectNode o = ownerNode();', 'o.put("telephone", "12345");',
     'createOwner(o).andExpect(status().isBadRequest());'])],
 "telephone-unique": [
   ("coreRejectsDuplicateTelephone", ['ObjectNode a = ownerNode();', 'createOwnerOk(a);',
     'ObjectNode b = ownerNode();', 'b.put("telephone", a.get("telephone").asText());',
     'createOwner(b).andExpect(status().isConflict());'])],
 "email-format": [
   ("coreLowercasesEmail", ['ObjectNode o = ownerNode();', 'o.put("email", "Test.User@Example.COM");',
     'int id = createOwnerOk(o);', 'getOwner(id).andExpect(jsonPath("$.email").value("test.user@example.com"));']),
   ("errorRejectsInvalidEmail", ['ObjectNode o = ownerNode();', 'o.put("email", "not-an-email");',
     'createOwner(o).andExpect(status().isBadRequest());'])],
 "display-name": [
   ("coreComputesDisplayName", ['ObjectNode o = ownerNode();', 'o.put("firstName", "John");',
     'String last = o.get("lastName").asText();', 'int id = createOwnerOk(o);',
     'getOwner(id).andExpect(jsonPath("$.displayName").value(last + ", John"));'])],
 "initials": [
   ("coreComputesInitials", ['ObjectNode o = ownerNode();', 'o.put("firstName", "John");', 'o.put("lastName", "smith");',
     'int id = createOwnerOk(o);', 'getOwner(id).andExpect(jsonPath("$.initials").value("J.S."));'])],
 "registration-date": [
   ("coreDefaultsToToday", ['int id = createOwnerOk(ownerNode());',
     'getOwner(id).andExpect(jsonPath("$.registrationDate").value(today()));'])],
 "telephone-e164": [
   ("coreStoresE164", ['ObjectNode o = ownerNode();', 'o.put("telephone", "0412 345 678");',
     'int id = createOwnerOk(o);', 'JsonNode n = fetchOwner(id);',
     'assertTrue(n.get("telephone").asText().startsWith("+")); // TODO: assert exact E.164, default +61']),
   ("errorRejectsUnformattable", ['ObjectNode o = ownerNode();', 'o.put("telephone", "12");',
     'createOwner(o).andExpect(status().isBadRequest());'])],
 "customer-code": [
   ("coreAssignsCustomerCode", ['int id = createOwnerOk(ownerNode());', 'JsonNode n = fetchOwner(id);',
     'assertTrue(n.get("customerCode").asText().matches("[A-Z]{3}-\\\\d{4}")); // <LAST3>-<NNNN>'])],
 "household-duplicate": [
   ("coreRejectsSameLastNameAndAddress", ['ObjectNode a = ownerNode();', 'createOwnerOk(a);', 'ObjectNode b = ownerNode();',
     'b.put("lastName", a.get("lastName").asText());', 'b.put("address", a.get("address").asText());',
     'createOwner(b).andExpect(status().isConflict());'])],
 "shares-household": [
   ("coreSharesHouseholdId", ['ObjectNode a = ownerNode();', 'int ida = createOwnerOk(a);', 'ObjectNode b = ownerNode();',
     'b.put("lastName", a.get("lastName").asText());', 'b.put("address", a.get("address").asText());',
     'b.put("sharesHousehold", true);', 'int idb = createOwnerOk(b);',
     'assertEquals(fetchOwner(ida).get("householdId").asText(), fetchOwner(idb).get("householdId").asText());'])],
 "address-normalize": [
   ("coreNormalizesAddress", ['ObjectNode o = ownerNode();', 'o.put("address", "  12  main  st ");',
     'int id = createOwnerOk(o);', 'getOwner(id).andExpect(jsonPath("$.address").value("12 MAIN STREET"));'])],
 "namesake-count": [
   ("coreCountsNamesakes", ['ObjectNode a = ownerNode();', 'a.put("firstName", "Ann"); a.put("lastName", "namesake");',
     'createOwnerOk(a);', 'ObjectNode b = ownerNode();', 'b.put("firstName", "Ann"); b.put("lastName", "namesake");',
     'int id = createOwnerOk(b);', 'getOwner(id).andExpect(jsonPath("$.namesakeCount").value(1));'])],
 "membership-number": [
   ("coreAssignsMembershipNumber", ['int id = createOwnerOk(ownerNode());',
     'getOwner(id).andExpect(jsonPath("$.membershipNumber").exists()); // TODO: <customerCode>-M<YY>'])],
 "membership-tier": [
   ("coreSilverWhenUniqueWithEmail", ['ObjectNode o = ownerNode();', 'o.put("firstName", "Uniq"); o.put("lastName", "solotier");',
     'o.put("email", uniqueEmail());', 'int id = createOwnerOk(o);',
     'getOwner(id).andExpect(jsonPath("$.membershipTier").value("SILVER"));']),
   ("functionalityBronzeWhenNoEmail", ['int id = createOwnerOk(ownerNode());',
     'getOwner(id).andExpect(jsonPath("$.membershipTier").value("BRONZE"));'])],
 "customer-code-city": [
   ("coreCustomerCodeHasCityPrefix", ['int id = createOwnerOk(ownerNode());', 'JsonNode n = fetchOwner(id);',
     'assertTrue(n.get("customerCode").asText().matches("[A-Z]{3}-[A-Z]{3}-\\\\d{4}")); // <CITY3>-<LAST3>-<NNNN>'])],
 "locality": [
   ("coreDerivesLocality", ['int id = createOwnerOk(ownerNode());',
     'getOwner(id).andExpect(jsonPath("$.locality").exists()); // unknown city -> "UNKNOWN"'])],
 "city-capacity": [
   ("coreRejectsWhenCityFull", ['// TODO: seed a city to 50 owners, then expect 409',
     'getOwner(createOwnerOk(ownerNode())); // placeholder create'])],
 "daily-limit": [
   ("coreRejectsOver100Today", ['// TODO: reach 100 creates today, then expect 429',
     'createOwner(ownerNode()).andExpect(status().is2xxSuccessful()); // placeholder'])],
 "business-day": [
   ("coreRegistrationRollsToBusinessDay", ['int id = createOwnerOk(ownerNode());',
     'getOwner(id).andExpect(jsonPath("$.registrationDate").exists()); // TODO: assert Mon when server date is weekend'])],
 "audit-create": [
   ("coreLogsAuditOnCreate", ['try (AuditLogCapture audit = new AuditLogCapture()) {',
     '\tint id = createOwnerOk(ownerNode());',
     '\tassertTrue(audit.anyContains(String.valueOf(id))); // TODO: also customerCode + registrationDate', '}'])],
 "bulk-warning": [
   ("coreBulkWarningFalseNormally", ['int id = createOwnerOk(ownerNode());',
     'getOwner(id).andExpect(jsonPath("$.bulkSignupWarning").value(false)); // TODO: true when >80 today'])],
 "tier-gold": [
   ("coreGoldForLargeHousehold", ['// TODO: build a 3-member household, expect GOLD',
     'int id = createOwnerOk(ownerNode());', 'getOwner(id).andExpect(jsonPath("$.membershipTier").exists());'])],
 "membership-levels": [
   ("coreNumericLevel", ['ObjectNode o = ownerNode();', 'o.put("firstName", "Uniq"); o.put("lastName", "levelsolo");',
     'o.put("email", uniqueEmail());', 'int id = createOwnerOk(o);',
     'getOwner(id).andExpect(jsonPath("$.membershipLevel").value(3)); // 1 +email +namesake0, capped 3'])],
 "email-unique": [
   ("coreRejectsDuplicateEmail", ['ObjectNode a = ownerNode();', 'a.put("email", uniqueEmail());', 'createOwnerOk(a);',
     'ObjectNode b = ownerNode();', 'b.put("email", a.get("email").asText());',
     'createOwner(b).andExpect(status().isConflict());'])],
 "telephone-country-length": [
   ("errorRejectsWrongNationalLength", ['ObjectNode o = ownerNode();', 'o.put("telephone", "+61 123");',
     'createOwner(o).andExpect(status().isBadRequest()); // +61 needs 9 national digits'])],
 "contact-preference": [
   ("corePhoneWhenNoEmail", ['int id = createOwnerOk(ownerNode());',
     'getOwner(id).andExpect(jsonPath("$.contactPreference").value("PHONE"));']),
   ("functionalityEmailWhenPresent", ['ObjectNode o = ownerNode();', 'o.put("email", uniqueEmail());',
     'int id = createOwnerOk(o);', 'getOwner(id).andExpect(jsonPath("$.contactPreference").value("EMAIL"));'])],
 "identity-key": [
   ("coreRejectsIdentityCollision", ['ObjectNode a = ownerNode();', 'createOwnerOk(a);', 'ObjectNode b = ownerNode();',
     'b.put("telephone", a.get("telephone").asText());',
     'createOwner(b).andExpect(status().isConflict()); // same identityKey'])],
 "postcode": [
   ("errorRejectsMismatchedPostcode", ['ObjectNode o = ownerNode();', 'o.put("postcode", "9999");',
     'createOwner(o).andExpect(status().isBadRequest()); // TODO: postcode not valid for city'])],
 "locality-postcode": [
   ("coreLocalityFromPostcode", ['int id = createOwnerOk(withPostcode(ownerNode()));',
     'getOwner(id).andExpect(jsonPath("$.locality").exists()); // TODO: region resolved by postcode'])],
 "check-digit": [
   ("coreReturnsCheckDigit", ['int id = createOwnerOk(ownerNode());',
     'getOwner(id).andExpect(jsonPath("$.checkDigit").exists()); // Luhn over customerCode digits'])],
 "global-id": [
   ("coreCustomerCodeIsRegionHash", ['int id = createOwnerOk(withPostcode(ownerNode()));', 'JsonNode n = fetchOwner(id);',
     'assertTrue(n.get("customerCode").asText().matches("[A-Z0-9]+-[0-9A-F]{8}")); // <REGION>-<HASH8>'])],
 "no-future-date": [
   ("errorRejectsFutureDate", ['ObjectNode o = ownerNode();', 'o.put("registrationDate", "2999-01-01");',
     'createOwner(o).andExpect(status().isBadRequest());'])],
 "age-band": [
   ("coreDerivesAgeBand", ['ObjectNode o = ownerNode();', 'o.put("birthDate", "1990-01-01");',
     'int id = createOwnerOk(o);', 'getOwner(id).andExpect(jsonPath("$.ageBand").value("ADULT"));'])],
 "soft-match": [
   ("coreFlagsPossibleDuplicate", ['int id = createOwnerOk(ownerNode());',
     'getOwner(id).andExpect(jsonPath("$.possibleDuplicate").value(false)); // TODO: true on lastName+postcode near-match'])],
 "household-hash": [
   ("coreDeterministicHouseholdId", ['int id = createOwnerOk(withPostcode(ownerNode()));',
     'getOwner(id).andExpect(jsonPath("$.householdId").exists()); // sha256(lastName|postcode)[0:12]'])],
 "telephone-display": [
   ("coreFormatsTelephoneDisplay", ['int id = createOwnerOk(ownerNode());',
     'getOwner(id).andExpect(jsonPath("$.telephoneDisplay").exists()); // "+CC nnn nnn nnn"'])],
 "email-blocklist": [
   ("errorRejectsDisposableDomain", ['ObjectNode o = ownerNode();', 'o.put("email", "x@mailinator.com");',
     'createOwner(o).andExpect(status().isBadRequest());'])],
 "tenure-cap": [
   ("coreNewOwnerCappedAtLevel3", ['// even with all factors, a brand-new owner has zero tenure',
     'int id = createOwnerOk(withPostcode(ownerNode()));',
     'getOwner(id).andExpect(jsonPath("$.membershipLevel").exists()); // TODO: assert <= 3'])],
 "membership-points": [
   ("coreReturnsPointsAndLevel", ['ObjectNode o = withPostcode(ownerNode());', 'o.put("email", uniqueEmail());',
     'int id = createOwnerOk(o);', 'getOwner(id).andExpect(jsonPath("$.membershipPoints").exists())',
     '\t\t.andExpect(jsonPath("$.membershipLevel").exists()); // TODO: assert mapping'])],
 "code-collision": [
   ("coreDeduplicatesCustomerCode", ['// TODO: force a hash collision, expect "-2" suffix',
     'int id = createOwnerOk(withPostcode(ownerNode()));', 'getOwner(id).andExpect(jsonPath("$.customerCode").exists());'])],
 "locality-timezone": [
   ("coreReturnsTimezone", ['int id = createOwnerOk(withPostcode(ownerNode()));',
     'getOwner(id).andExpect(jsonPath("$.timezone").exists()); // IANA name'])],
 "audit-enriched": [
   ("coreAuditIncludesLevelAndNumber", ['try (AuditLogCapture audit = new AuditLogCapture()) {',
     '\tint id = createOwnerOk(withPostcode(ownerNode()));',
     '\tassertTrue(audit.count() > 0); // TODO: assert membershipLevel + membershipNumber present', '}'])],
 "address-structured": [
   ("coreAcceptsStructuredAddress", ['ObjectNode o = structuredOwner();', 'int id = createOwnerOk(o);',
     'getOwner(id).andExpect(jsonPath("$.addressLine1").exists())',
     '\t\t.andExpect(jsonPath("$.address").exists()); // composed string'])],
 "salutation": [
   ("coreComposesSalutation", ['ObjectNode o = structuredOwner();', 'o.put("title", "DR"); o.put("lastName", "who");',
     'int id = createOwnerOk(o);', 'getOwner(id).andExpect(jsonPath("$.salutation").value("DR who"));'])],
 "exclude-deleted": [
   ("coreIgnoresDeletedOnDuplicate", ['// TODO: create, soft-delete, then a matching create should succeed',
     'int id = createOwnerOk(structuredOwner());', 'getOwner(id).andExpect(status().is2xxSuccessful());'])],
 "holiday-business-day": [
   ("coreRollsPastHoliday", ['int id = createOwnerOk(structuredOwner());',
     'getOwner(id).andExpect(jsonPath("$.registrationDate").exists()); // TODO: skips public holiday'])],
 "fiscal-year": [
   ("coreReturnsFiscalYear", ['int id = createOwnerOk(structuredOwner());', 'JsonNode n = fetchOwner(id);',
     'assertTrue(n.get("fiscalYear").asText().matches("FY\\\\d{2}"));'])],
 "self-link": [
   ("coreReturnsSelfLink", ['int id = createOwnerOk(structuredOwner());',
     'getOwner(id).andExpect(jsonPath("$.selfLink").value("/api/owners/" + id));'])],
 "idempotency": [
   ("coreIdempotentRepeat", ['// TODO: POST twice with the same Idempotency-Key header, expect same owner + 200',
     'int id = createOwnerOk(structuredOwner());', 'getOwner(id).andExpect(status().is2xxSuccessful());'])],
 "level-ceiling": [
   ("coreCapsLevelByHousehold", ['// TODO: existing high-level household member caps a new member',
     'int id = createOwnerOk(structuredOwner());', 'getOwner(id).andExpect(jsonPath("$.membershipLevel").exists());'])],
 "identity-key-v2": [
   ("coreIdentityKeyV2Collision", ['ObjectNode a = structuredOwner();', 'createOwnerOk(a);', 'ObjectNode b = structuredOwner();',
     'b.put("telephone", a.get("telephone").asText());',
     'createOwner(b).andExpect(status().isConflict()); // TODO: soundex-based key'])],
 "audit-event": [
   ("coreEmitsSequencedEvent", ['try (AuditLogCapture audit = new AuditLogCapture()) {',
     '\tcreateOwnerOk(structuredOwner());',
     '\tassertTrue(audit.anyContains("OWNER_CREATED")); // TODO: assert monotonically increasing seq', '}'])],
 "capacity-warning": [
   ("coreCapacityWarningFalseNormally", ['int id = createOwnerOk(structuredOwner());',
     'getOwner(id).andExpect(jsonPath("$.capacityWarning").value(false)); // TODO: true at 40-49'])],
 "owner-segment": [
   ("coreReturnsOwnerSegment", ['int id = createOwnerOk(structuredOwner());',
     'getOwner(id).andExpect(jsonPath("$.ownerSegment").exists());'])],
 "member-id": [
   ("coreReturnsUnifiedMemberId", ['int id = createOwnerOk(structuredOwner());', 'JsonNode n = fetchOwner(id);',
     'assertTrue(n.has("memberId")); // TODO: <REGION><FY><HASH8><CHK>',
     'assertTrue(!n.has("customerCode") && !n.has("membershipNumber")); // removed'])],
 "welcome-notify": [
   ("coreEnqueuesWelcome", ['try (AuditLogCapture notify = new AuditLogCapture("NOTIFY")) {',
     '\tint id = createOwnerOk(structuredOwner());',
     '\tassertTrue(notify.anyContains(String.valueOf(id))); // TODO: also memberId', '}'])],
 "risk-flag": [
   ("coreRiskFlagFalseNormally", ['int id = createOwnerOk(structuredOwner());',
     'getOwner(id).andExpect(jsonPath("$.riskFlag").value(false));'])],
 "problem-json": [
   ("coreRejectionIsProblemJson", ['ObjectNode o = structuredOwner();', 'o.remove("city");',
     'createOwner(o).andExpect(status().isBadRequest())',
     '\t\t.andExpect(jsonPath("$.title").exists()); // RFC7807 problem+json'])],
 "identity-v2": [
   ("coreV2GroupsIdentityAndVersions", ['int id = createOwnerOk(structuredOwner());',
     'getOwner(id).andExpect(jsonPath("$.apiVersion").value(2))',
     '\t\t.andExpect(jsonPath("$.identity.memberId").exists())',
     '\t\t.andExpect(jsonPath("$.identity.householdId").exists())',
     '\t\t.andExpect(jsonPath("$.memberId").doesNotExist()); // moved under identity'])],
}

# extra helpers referenced above, appended to AcceptanceBase via a small mixin note
HELPERS = {"withPostcode", "structuredOwner"}

def imports_for(bodies):
    txt = "\n".join(bodies)
    imp = ['import org.junit.jupiter.api.Tag;', 'import org.junit.jupiter.api.Test;']
    if "jsonPath" in txt:
        imp.append('import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;')
    if "status(" in txt:
        imp.append('import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;')
    for a in ("assertTrue", "assertEquals", "assertFalse", "assertNotNull"):
        if a + "(" in txt:
            imp.append(f'import static org.junit.jupiter.api.Assertions.{a};')
    if "ObjectNode" in txt:
        imp.append('import tools.jackson.databind.node.ObjectNode;')
    if "JsonNode" in txt:
        imp.append('import tools.jackson.databind.JsonNode;')
    # de-dup keep order
    seen = set(); out = []
    for i in imp:
        if i not in seen:
            seen.add(i); out.append(i)
    return out

def build_class(nn, tag, class_name, header, methods):
    bodies = [ln for _, body in methods for ln in body]
    imp = imports_for(bodies)
    L = [f"package {PKG};", ""]
    L += imp + ["", f"/** {header} */", f'@Tag("{tag}")', f"class {class_name} extends AcceptanceBase {{"]
    for name, body in methods:
        L += ["", "\t@Test", f"\tvoid {name}() throws Exception {{"]
        L += ["\t\t" + ln for ln in body]
        L.append("\t}")
    L += ["}", ""]
    return "\n".join(L)

# --- fully authored slice: cp1-12 primaries (tight assertions, the pattern) ---
M_FULL = {
 "required-fields": [
   ("errorRejectsMissingCity", ['ObjectNode o = ownerNode();', 'o.remove("city");',
     'createOwner(o).andExpect(status().isBadRequest())',
     '\t\t.andExpect(jsonPath("$.errors").value(org.hamcrest.Matchers.hasItem("city")));']),
   ("errorRejectsBlankTelephone", ['ObjectNode o = ownerNode();', 'o.put("telephone", "   ");',
     'createOwner(o).andExpect(status().isBadRequest());']),
   ("functionalityAcceptsCompleteOwner", ['createOwner(ownerNode()).andExpect(status().is2xxSuccessful());'])],
 "telephone-normalize": [
   ("coreStripsToTenDigits", ['ObjectNode o = ownerNode();', 'o.put("telephone", "(04) 1234-5678");',
     'int id = createOwnerOk(o);', 'getOwner(id).andExpect(jsonPath("$.telephone").value("0412345678"));']),
   ("errorRejectsTooFewDigits", ['ObjectNode o = ownerNode();', 'o.put("telephone", "12345");',
     'createOwner(o).andExpect(status().isBadRequest());'])],
 "telephone-unique": [
   ("coreRejectsDuplicateTelephone", ['ObjectNode a = ownerNode();', 'createOwnerOk(a);', 'ObjectNode b = ownerNode();',
     'b.put("telephone", a.get("telephone").asText());', 'createOwner(b).andExpect(status().isConflict());']),
   ("functionalityAllowsDistinctTelephone", ['createOwnerOk(ownerNode());',
     'createOwner(ownerNode()).andExpect(status().is2xxSuccessful());'])],
 "email-format": [
   ("coreLowercasesEmail", ['ObjectNode o = ownerNode();', 'o.put("email", "Test.User@Example.COM");',
     'int id = createOwnerOk(o);', 'getOwner(id).andExpect(jsonPath("$.email").value("test.user@example.com"));']),
   ("errorRejectsInvalidEmail", ['ObjectNode o = ownerNode();', 'o.put("email", "not-an-email");',
     'createOwner(o).andExpect(status().isBadRequest());']),
   ("functionalityAcceptsMissingEmail", ['createOwner(ownerNode()).andExpect(status().is2xxSuccessful());'])],
 "display-name": [
   ("coreComputesDisplayName", ['ObjectNode o = ownerNode();', 'o.put("firstName", "John");',
     'String last = o.get("lastName").asText();', 'int id = createOwnerOk(o);',
     'getOwner(id).andExpect(jsonPath("$.displayName").value(last + ", John"));'])],
 "initials": [
   ("coreComputesInitials", ['ObjectNode o = ownerNode();', 'o.put("firstName", "john"); o.put("lastName", "smith");',
     'int id = createOwnerOk(o);', 'getOwner(id).andExpect(jsonPath("$.initials").value("J.S."));'])],
 "registration-date": [
   ("coreDefaultsToToday", ['int id = createOwnerOk(ownerNode());',
     'getOwner(id).andExpect(jsonPath("$.registrationDate").value(today()));']),
   ("functionalityKeepsSuppliedDate", ['ObjectNode o = ownerNode();', 'o.put("registrationDate", "2020-06-15");',
     'int id = createOwnerOk(o);', 'getOwner(id).andExpect(jsonPath("$.registrationDate").value("2020-06-15"));'])],
 "telephone-e164": [
   ("coreNationalToE164", ['ObjectNode o = ownerNode();', 'o.put("telephone", "0412 345 678");',
     'int id = createOwnerOk(o);', 'getOwner(id).andExpect(jsonPath("$.telephone").value("+61412345678"));']),
   ("functionalityKeepsExplicitCountryCode", ['ObjectNode o = ownerNode();', 'o.put("telephone", "+64 21 123 456");',
     'int id = createOwnerOk(o);', 'getOwner(id).andExpect(jsonPath("$.telephone").value("+6421123456"));']),
   ("errorRejectsUnformattable", ['ObjectNode o = ownerNode();', 'o.put("telephone", "12");',
     'createOwner(o).andExpect(status().isBadRequest());'])],
 "customer-code": [
   ("coreFormatAndGlobalSequence", ['ObjectNode a = ownerNode(); a.put("lastName", "smithers");',
     'int ida = createOwnerOk(a);', 'ObjectNode b = ownerNode(); b.put("lastName", "jones");', 'int idb = createOwnerOk(b);',
     'String ca = fetchOwner(ida).get("customerCode").asText();', 'String cb = fetchOwner(idb).get("customerCode").asText();',
     'assertTrue(ca.startsWith("SMI-"), ca);', 'assertTrue(cb.startsWith("JON-"), cb);',
     'assertEquals(Integer.parseInt(ca.substring(4)) + 1, Integer.parseInt(cb.substring(4)));'])],
 "household-duplicate": [
   ("coreRejectsSameLastNameAndAddress", ['ObjectNode a = ownerNode();', 'createOwnerOk(a);', 'ObjectNode b = ownerNode();',
     'b.put("lastName", a.get("lastName").asText()); b.put("address", a.get("address").asText());',
     'createOwner(b).andExpect(status().isConflict());']),
   ("functionalityAllowsDifferentAddress", ['ObjectNode a = ownerNode();', 'createOwnerOk(a);', 'ObjectNode b = ownerNode();',
     'b.put("lastName", a.get("lastName").asText());', 'createOwner(b).andExpect(status().is2xxSuccessful());']),
   ("functionalityAllowsWithSharesHousehold", ['ObjectNode a = ownerNode();', 'createOwnerOk(a);', 'ObjectNode b = ownerNode();',
     'b.put("lastName", a.get("lastName").asText()); b.put("address", a.get("address").asText());',
     'b.put("sharesHousehold", true);', 'createOwner(b).andExpect(status().is2xxSuccessful());'])],
 "shares-household": [
   ("coreJoinersShareHouseholdId", ['ObjectNode a = ownerNode();', 'createOwnerOk(a);',
     'ObjectNode b = ownerNode(); b.put("lastName", a.get("lastName").asText());',
     'b.put("address", a.get("address").asText()); b.put("sharesHousehold", true);', 'int idb = createOwnerOk(b);',
     'ObjectNode c = ownerNode(); c.put("lastName", a.get("lastName").asText());',
     'c.put("address", a.get("address").asText()); c.put("sharesHousehold", true);', 'int idc = createOwnerOk(c);',
     'String hb = fetchOwner(idb).get("householdId").asText();',
     'assertEquals(hb, fetchOwner(idc).get("householdId").asText());', 'assertTrue(!hb.isBlank());'])],
 "address-normalize": [
   ("coreNormalizesWhitespaceAndCase", ['ObjectNode o = ownerNode();', 'o.put("address", "  12  main  st ");',
     'int id = createOwnerOk(o);', 'getOwner(id).andExpect(jsonPath("$.address").value("12 MAIN STREET"));']),
   ("functionalityExpandsAbbreviations", ['ObjectNode o = ownerNode();', 'o.put("address", "7 elm ave");',
     'int id = createOwnerOk(o);', 'getOwner(id).andExpect(jsonPath("$.address").value("7 ELM AVENUE"));']),
   ("errorRejectsBlankAfterNormalize", ['ObjectNode o = ownerNode();', 'o.put("address", "   ");',
     'createOwner(o).andExpect(status().isBadRequest());'])],
}
M.update(M_FULL)

# --- fully authored replacement bodies for the cp08/ and cp12/ mutations ---
# keyed by (mutation checkpoint number, prior checkpoint number) -> (header, methods)
REPL = {
 (8, 2): ("cp02 telephone-normalize: UPDATED by cp08 (telephone-e164) — telephone is stored in E.164 form.", [
   ("coreStoresE164", ['ObjectNode o = ownerNode();', 'o.put("telephone", "0412 345 678");',
     'int id = createOwnerOk(o);', 'getOwner(id).andExpect(jsonPath("$.telephone").value("+61412345678"));']),
   ("errorRejectsUnformattable", ['ObjectNode o = ownerNode();', 'o.put("telephone", "12");',
     'createOwner(o).andExpect(status().isBadRequest());'])]),
 (8, 3): ("cp03 telephone-unique: UPDATED by cp08 — duplicate telephones are compared as E.164.", [
   ("coreRejectsDuplicateAcrossFormats", ['// national and international forms of the same number must collide',
     'ObjectNode a = ownerNode(); a.put("telephone", "0412 345 678");', 'createOwnerOk(a);',
     'ObjectNode b = ownerNode(); b.put("telephone", "+61 412 345 678");',
     'createOwner(b).andExpect(status().isConflict());'])]),
 (12, 1): ("cp01 required-fields: UPDATED by cp12 (address-normalize) — an address blank after normalization is rejected.", [
   ("coreRejectsWhitespaceOnlyAddress", ['ObjectNode o = ownerNode();', 'o.put("address", "   ");',
     'createOwner(o).andExpect(status().isBadRequest());']),
   ("errorStillRejectsMissingCity", ['ObjectNode o = ownerNode();', 'o.remove("city");',
     'createOwner(o).andExpect(status().isBadRequest());'])]),
 (12, 10): ("cp10 household-duplicate: UPDATED by cp12 — addresses are compared after normalization.", [
   ("coreRejectsAddressesThatNormalizeEqual", ['ObjectNode a = ownerNode(); a.put("address", "12 Main St");',
     'createOwnerOk(a);', 'ObjectNode b = ownerNode(); b.put("lastName", a.get("lastName").asText());',
     'b.put("address", "12  main  street");', 'createOwner(b).andExpect(status().isConflict());'])]),
 (12, 11): ("cp11 shares-household: UPDATED by cp12 — householdId is derived from the normalized address.", [
   ("coreSameHouseholdIdForNormalizedEqualAddresses", ['ObjectNode a = ownerNode(); a.put("address", "12 Main St");',
     'createOwnerOk(a);', 'ObjectNode b = ownerNode(); b.put("lastName", a.get("lastName").asText());',
     'b.put("address", "12 main street"); b.put("sharesHousehold", true);', 'int idb = createOwnerOk(b);',
     'ObjectNode c = ownerNode(); c.put("lastName", a.get("lastName").asText());',
     'c.put("address", "12  MAIN  ST"); c.put("sharesHousehold", true);', 'int idc = createOwnerOk(c);',
     'assertEquals(fetchOwner(idb).get("householdId").asText(), fetchOwner(idc).get("householdId").asText());'])]),
}

# 1) primary CpNNTests.java
by_id = {cp["id"]: cp for cp in cps}
written = 0
for cp in cps:
    nn = f"{cp['n']:02d}"
    methods = M.get(cp["id"])
    if not methods:
        methods = [("coreTODO", [f'// TODO: assert the rule "{cp["id"]}"', 'int id = createOwnerOk(ownerNode());',
                                 'getOwner(id).andExpect(status().is2xxSuccessful());'])]
    header = f"cp{nn} {cp['id']}: {cp['spec'][:90].rstrip()}..."
    open(f"{DEST}/Cp{nn}Tests.java", "w").write(
        build_class(nn, f"cp{nn}", f"Cp{nn}Tests", header, methods))
    written += 1

# 2) cpNN/ replacement stubs for each mutative checkpoint
repl = 0
for cp in cps:
    if cp.get("type") != "mutative":
        continue
    nn = f"{cp['n']:02d}"
    sub = f"{DEST}/cp{nn}"
    shutil.rmtree(sub, ignore_errors=True)   # rebuild fresh so a changed manifest leaves no stale files
    os.makedirs(sub, exist_ok=True)
    change = cp["spec"].split(".")[0].strip()
    for mm in cp["mutates"]:
        mmn = f"{mm:02d}"
        rid = next((c["id"] for c in cps if c["n"] == mm), "")
        if (cp["n"], mm) in REPL:                       # fully authored replacement
            header, methods = REPL[(cp["n"], mm)]
        else:                                           # generic stub to fill in
            header = f"cp{mmn} {rid}: UPDATED by cp{nn} ({cp['id']}) — {change}"
            methods = [("coreUpdatedBehaviour", [
                f'// This rule changed. {change}.',
                f'// TODO: assert the UPDATED behaviour of "{rid}" under the new spec.',
                'int id = createOwnerOk(ownerNode());',
                'getOwner(id).andExpect(status().is2xxSuccessful());'])]
        open(f"{sub}/Cp{mmn}Tests.java", "w").write(
            build_class(mmn, f"cp{mmn}", f"Cp{mmn}Tests", header, methods))
        repl += 1

print(f"primary tests written: {written}")
print(f"replacement stubs written: {repl}")
print("helpers referenced but not yet in AcceptanceBase:", sorted(HELPERS),
      "\n  -> add withPostcode()/structuredOwner() to AcceptanceBase before running.")
