package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** cp23 tier-gold, UPDATED by cp36: household membership now keys off the computed householdId
 *  (lastName + postcode). Three members share it; the third (unique firstName, no email) is numeric
 *  membershipLevel 2 with no tier. */
@Tag("cp23")
class Cp23Tests extends AcceptanceBase {

	@Test
	void coreComputedHouseholdMemberHasLevel() throws Exception {
		String lastName = uniqueLastName();
		int last = 0;
		for (int i = 0; i < 3; i++) {
			ObjectNode m = ownerNode();
			m.put("firstName", "Mem" + i);
			m.put("lastName", lastName);
			m.put("postcode", "2000");
			m.put("sharesHousehold", true);
			last = createOwnerOk(m);
		}
		getOwner(last).andExpect(jsonPath("$.membershipTier").doesNotExist())
				.andExpect(jsonPath("$.membershipLevel").value(2));
	}
}
