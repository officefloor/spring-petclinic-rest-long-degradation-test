package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;

/** global-id: customerCode is replaced by memberId ('<REGION><FY><HASH8><CHK>').
 * The region prefix and computed HASH8 are exact; customerCode is gone. */
@Tag("cp32")
class Cp32Tests extends AcceptanceBase {

	@Test
	void coreMemberIdReplacesCustomerCode() throws Exception {
		JsonNode r = fetchOwner(createOwnerOk(knownOwner("Sydney")));
		String hash8 = shaHex(r.get("telephone").asText() + r.get("lastName").asText(), 8);
		String mid = r.get("memberId").asText();
		assertTrue(mid.startsWith("NSW"), mid);
		assertTrue(mid.contains(hash8), mid + " should contain " + hash8);
		assertTrue(!r.has("customerCode"), "customerCode removed");
	}
}
