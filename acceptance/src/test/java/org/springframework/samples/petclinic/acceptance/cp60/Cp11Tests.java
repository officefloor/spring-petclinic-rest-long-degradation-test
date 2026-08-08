package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import tools.jackson.databind.node.ObjectNode;

/** shares-household: householdId now lives under the nested 'identity' object.
 * Two owners with the same lastName + postcode still share it. */
@Tag("cp11")
class Cp11Tests extends AcceptanceBase {

	@Test
	void coreSharedHouseholdIdUnderIdentity() throws Exception {
		String lastName = uniqueLastName();
		ObjectNode a = structuredOwner();
		a.put("lastName", lastName);
		a.put("postcode", "2000");
		ObjectNode b = structuredOwner();
		b.put("lastName", lastName);
		b.put("postcode", "2000");
		b.put("sharesHousehold", true);
		String ha = fetchOwner(createOwnerOk(a)).get("identity").get("householdId").asText();
		String hb = fetchOwner(createOwnerOk(b)).get("identity").get("householdId").asText();
		assertEquals(ha, hb);
	}
}
