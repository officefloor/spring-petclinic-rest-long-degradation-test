package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;

/** global-id: Redesign owner identity. The customerCode must become '<REGION>-<HASH8>' where REGION is t... */
@Tag("cp32")
class Cp32Tests extends AcceptanceBase {

	@Test
	void coreCustomerCodeIsRegionHash() throws Exception {
		int id = createOwnerOk(withPostcode(ownerNode()));
		JsonNode n = fetchOwner(id);
		assertTrue(n.get("customerCode").asText().matches("[A-Z0-9]+-[0-9A-F]{8}")); // <REGION>-<HASH8>
	}
}
