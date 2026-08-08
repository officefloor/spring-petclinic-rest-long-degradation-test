package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import tools.jackson.databind.JsonNode;

/** customer-code: customerCode = '<REGION>-<HASH8>', REGION from the postcode,
 * HASH8 = SHA-256(telephone + lastName)[0:8] upper hex. Recomputed exactly from the response. */
@Tag("cp09")
class Cp09Tests extends AcceptanceBase {

	@Test
	void coreCustomerCodeIsRegionAndHash() throws Exception {
		JsonNode r = fetchOwner(createOwnerOk(knownOwner("Sydney"))); // postcode 2000 -> NSW
		String hash8 = shaHex(r.get("telephone").asText() + r.get("lastName").asText(), 8);
		assertEquals("NSW-" + hash8, r.get("customerCode").asText());
	}
}
