package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.JsonNode;

/** cp16 customer-code-city: Change the customerCode format to '<CITY3>-<LAST3>-<NNNN>' where CITY3 is the upper-cased... */
@Tag("cp16")
class Cp16Tests extends AcceptanceBase {

	@Test
	void coreCustomerCodeHasCityPrefix() throws Exception {
		int id = createOwnerOk(ownerNode());
		JsonNode n = fetchOwner(id);
		assertTrue(n.get("customerCode").asText().matches("[A-Z]{3}-[A-Z]{3}-\\d{4}")); // <CITY3>-<LAST3>-<NNNN>
	}
}
