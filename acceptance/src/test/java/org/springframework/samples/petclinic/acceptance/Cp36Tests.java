package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import tools.jackson.databind.node.ObjectNode;

/** household-hash: householdId is deterministic from (lastName, postcode) alone. Asserting the
 * exact hash would couple to the internal normalization, so assert the observable contract: same
 * lastName+postcode -> same householdId; a different lastName -> a different householdId. */
@Tag("cp36")
class Cp36Tests extends AcceptanceBase {

	@Test
	void coreSameLastNameAndPostcodeShareHouseholdId() throws Exception {
		String lastName = uniqueLastName();
		ObjectNode a = ownerNode();
		a.put("lastName", lastName);
		a.put("postcode", "2000");
		ObjectNode b = ownerNode();
		b.put("lastName", lastName);
		b.put("postcode", "2000");
		b.put("sharesHousehold", true); // same household -> bypass the duplicate block
		String ha = fetchOwner(createOwnerOk(a)).get("householdId").asText();
		String hb = fetchOwner(createOwnerOk(b)).get("householdId").asText();
		assertEquals(ha, hb);

		ObjectNode c = ownerNode(); // different lastName, same postcode
		c.put("postcode", "2000");
		String hc = fetchOwner(createOwnerOk(c)).get("householdId").asText();
		assertNotEquals(ha, hc);
	}
}
