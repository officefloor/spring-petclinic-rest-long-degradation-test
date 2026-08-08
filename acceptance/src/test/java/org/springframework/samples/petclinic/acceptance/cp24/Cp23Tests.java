package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** tier-gold: the GOLD tier is gone. A 3-member household no longer yields a
 * tier; the third member (unique firstName -> namesake 0, no email) is numeric membershipLevel 2. */
@Tag("cp23")
class Cp23Tests extends AcceptanceBase {

	@Test
	void coreHouseholdMemberHasNumericLevelNotTier() throws Exception {
		String lastName = uniqueLastName();
		String address = uniqueAddress();
		int last = 0;
		for (int i = 0; i < 3; i++) {
			ObjectNode m = ownerNode();
			m.put("firstName", uniqueFirstName()); // unique letters-only names -> namesakeCount 0 each
			m.put("lastName", lastName);
			m.put("address", address);
			m.put("sharesHousehold", true);
			last = createOwnerOk(m);
		}
		getOwner(last).andExpect(jsonPath("$.membershipTier").doesNotExist())
				.andExpect(jsonPath("$.membershipLevel").value(2)); // 1 + namesake 0, no email
	}
}
