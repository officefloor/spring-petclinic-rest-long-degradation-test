package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** tenure-cap: level 4 needs 6+ points, and the only route to 6 is tenure
 * (+3), which a new owner (zero tenure) never has. A new owner with every other factor maxed scores
 * 5 points -> level 3, never 4. */
@Tag("cp39")
class Cp39Tests extends AcceptanceBase {

	@Test
	void coreNewOwnerCappedBelowFour() throws Exception {
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
		getOwner(last).andExpect(jsonPath("$.membershipLevel").value(3)); // 5 points, zero tenure -> not 4
	}
}
