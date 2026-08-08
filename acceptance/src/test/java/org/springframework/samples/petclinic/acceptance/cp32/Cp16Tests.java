package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import tools.jackson.databind.JsonNode;

/** customer-code-city: the city-prefixed sequence format is gone, replaced by
 * '<REGION>-<HASH8>'. Assert the exact region-and-hash value. */
@Tag("cp16")
class Cp16Tests extends AcceptanceBase {

	@Test
	void coreCustomerCodeIsRegionAndHashNotCitySequence() throws Exception {
		JsonNode r = fetchOwner(createOwnerOk(knownOwner("Sydney")));
		String hash8 = shaHex(r.get("telephone").asText() + r.get("lastName").asText(), 8);
		assertEquals("NSW-" + hash8, r.get("customerCode").asText());
	}
}
