package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;

/** cp56 member-id: Unify the customerCode and membershipNumber into a single 'memberId' formatted '<REGION><F... */
@Tag("cp56")
class Cp56Tests extends AcceptanceBase {

	@Test
	void coreReturnsUnifiedMemberId() throws Exception {
		int id = createOwnerOk(structuredOwner());
		JsonNode n = fetchOwner(id);
		assertTrue(n.has("memberId")); // TODO: <REGION><FY><HASH8><CHK>
		assertTrue(!n.has("customerCode") && !n.has("membershipNumber")); // removed
	}
}
