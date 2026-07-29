package org.springframework.samples.petclinic.acceptance;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import tools.jackson.databind.node.ObjectNode;

/** cp10: customerCode = "<UPPERCASE_CITY>-<NNNN>", NNNN = per-city sequence. */
@Tag("cp10")
class Cp10Tests extends AcceptanceBase {

	@Test
	void coreCustomerCodePerCitySequence() throws Exception {
		String city = "Zedton" + seq();      // a city with no existing owners
		String prefix = city.toUpperCase() + "-";

		ObjectNode a = ownerNode();
		a.put("city", city);
		String codeA = fetchOwner(createOwnerOk(a)).get("customerCode").asText();

		ObjectNode b = ownerNode();
		b.put("city", city);
		String codeB = fetchOwner(createOwnerOk(b)).get("customerCode").asText();

		assertTrue(codeA.startsWith(prefix), "code should start with the uppercased city: " + codeA);
		assertEquals(prefix + "0001", codeA);
		assertEquals(prefix + "0002", codeB);
	}
}
