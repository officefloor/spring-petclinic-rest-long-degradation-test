package org.springframework.samples.petclinic.acceptance;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import tools.jackson.databind.node.ObjectNode;

/** cp17: sharesHousehold = another owner already has the same address and city. */
@Tag("cp17")
class Cp17Tests extends AcceptanceBase {

	@Test
	void coreHouseholdFlag() throws Exception {
		String address = uniqueAddress();
		String city = uniqueCity();

		ObjectNode a = ownerNode();
		a.put("address", address);
		a.put("city", city);
		boolean first = fetchOwner(createOwnerOk(a)).get("sharesHousehold").asBoolean();

		ObjectNode b = ownerNode(); // same address + city, own unique name/phone
		b.put("address", address);
		b.put("city", city);
		boolean second = fetchOwner(createOwnerOk(b)).get("sharesHousehold").asBoolean();

		assertFalse(first, "first owner at the address shares no household");
		assertTrue(second, "second owner at the same address + city shares a household");
	}
}
