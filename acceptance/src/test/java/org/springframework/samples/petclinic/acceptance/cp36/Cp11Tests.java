package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import tools.jackson.databind.node.ObjectNode;

/** shares-household: householdId is computed from lastName + postcode, so
 * sharesHousehold only bypasses the block. Two same lastName+postcode owners share the householdId. */
@Tag("cp11")
class Cp11Tests extends AcceptanceBase {

	@Test
	void coreComputedHouseholdIdShared() throws Exception {
		String lastName = uniqueLastName();
		ObjectNode a = ownerNode();
		a.put("lastName", lastName);
		a.put("postcode", "2000");
		int ida = createOwnerOk(a);
		ObjectNode b = ownerNode();
		b.put("lastName", lastName);
		b.put("postcode", "2000");
		b.put("sharesHousehold", true); // bypass the duplicate block
		int idb = createOwnerOk(b);
		assertEquals(fetchOwner(ida).get("householdId").asText(),
				fetchOwner(idb).get("householdId").asText());
	}
}
