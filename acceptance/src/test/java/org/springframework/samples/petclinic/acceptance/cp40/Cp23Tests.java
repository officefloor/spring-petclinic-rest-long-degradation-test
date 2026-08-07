package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** cp23 tier-gold, UPDATED by cp40: a large household now adds points (not a GOLD tier). The third
 *  member of a household (same lastName+postcode) with an email scores 5 points
 *  (2 email + 1 namesake 0 + 2 household-of-3), mapping to level 3. */
@Tag("cp23")
class Cp23Tests extends AcceptanceBase {

	@Test
	void coreHouseholdAddsPoints() throws Exception {
		String lastName = uniqueLastName();
		int last = 0;
		for (int i = 0; i < 3; i++) {
			ObjectNode m = withPostcode(ownerNode());
			m.put("firstName", uniqueFirstName());
			m.put("lastName", lastName);
			m.put("sharesHousehold", true);
			if (i == 2) {
				m.put("email", uniqueEmail());
			}
			last = createOwnerOk(m);
		}
		getOwner(last).andExpect(jsonPath("$.membershipPoints").value(5))
				.andExpect(jsonPath("$.membershipLevel").value(3));
	}
}
