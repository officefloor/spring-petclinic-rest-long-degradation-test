package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import tools.jackson.databind.node.ObjectNode;

/** level-ceiling: a new owner's membershipLevel cannot exceed one above the current maximum
 * in their household. Two owners in the same household (same lastName + postcode): the second's
 * level must be at most the first's level + 1. */
@Tag("cp51")
class Cp51Tests extends AcceptanceBase {

	@Test
	void coreCapsLevelByHousehold() throws Exception {
		String lastName = uniqueLastName();
		ObjectNode a = structuredOwner();
		a.put("lastName", lastName);
		int ida = createOwnerOk(a);
		ObjectNode b = structuredOwner(); // same lastName + postcode -> same household, unique telephone
		b.put("lastName", lastName);
		b.put("email", uniqueEmail());
		int idb = createOwnerOk(b);
		int la = fetchOwner(ida).get("membershipLevel").asInt();
		int lb = fetchOwner(idb).get("membershipLevel").asInt();
		assertTrue(lb <= la + 1, "la=" + la + " lb=" + lb);
	}
}
