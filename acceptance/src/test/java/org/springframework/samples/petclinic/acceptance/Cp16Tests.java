package org.springframework.samples.petclinic.acceptance;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import tools.jackson.databind.node.ObjectNode;

/** cp16: namesakeCount = number of other owners with the same last name at creation. */
@Tag("cp16")
class Cp16Tests extends AcceptanceBase {

	@Test
	void coreCountsNamesakesAtCreation() throws Exception {
		String last = uniqueLastName(); // no existing owner has this surname
		ObjectNode a = ownerNode();
		a.put("lastName", last);
		int na = fetchOwner(createOwnerOk(a)).get("namesakeCount").asInt();

		ObjectNode b = ownerNode(); // same surname, own unique phone/city/email
		b.put("lastName", last);
		int nb = fetchOwner(createOwnerOk(b)).get("namesakeCount").asInt();

		assertEquals(0, na, "first owner with the surname has no namesakes");
		assertEquals(1, nb, "second owner with the surname has one namesake");
	}
}
