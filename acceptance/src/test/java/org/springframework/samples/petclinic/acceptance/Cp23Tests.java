package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** tier-gold: membershipTier is 'GOLD' when the owner's household has 3+ members after this
 * create. Build a shared household (same lastName + address, sharesHousehold) and assert the third
 * member is GOLD. */
@Tag("cp23")
class Cp23Tests extends AcceptanceBase {

	@Test
	void coreGoldForThreeMemberHousehold() throws Exception {
		String lastName = uniqueLastName();
		String address = uniqueAddress();
		for (int i = 0; i < 2; i++) {
			ObjectNode m = ownerNode();
			m.put("lastName", lastName);
			m.put("address", address);
			m.put("sharesHousehold", true);
			createOwnerOk(m);
		}
		ObjectNode third = ownerNode();
		third.put("lastName", lastName);
		third.put("address", address);
		third.put("sharesHousehold", true);
		int id = createOwnerOk(third);
		getOwner(id).andExpect(jsonPath("$.membershipTier").value("GOLD"));
	}
}
