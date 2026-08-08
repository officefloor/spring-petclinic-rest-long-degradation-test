package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;

/** member-id: customerCode and membershipNumber are unified into 'memberId' =
 * '<REGION><FY><HASH8><CHK>'. Assert the exact, computable sub-values: the pinned region prefix and
 * the SHA-256 HASH8 over (telephone + lastName); and that the two old fields are gone. */
@Tag("cp56")
class Cp56Tests extends AcceptanceBase {

	@Test
	void coreReturnsUnifiedMemberId() throws Exception {
		JsonNode r = fetchOwner(createOwnerOk(knownOwner("Sydney"))); // region NSW
		String hash8 = shaHex(r.get("telephone").asText() + r.get("lastName").asText(), 8);
		String memberId = r.get("memberId").asText();
		assertTrue(memberId.startsWith("NSW"), memberId);
		assertTrue(memberId.contains(hash8), memberId + " should contain " + hash8);
		assertTrue(!r.has("customerCode") && !r.has("membershipNumber"), "old id fields removed");
	}
}
