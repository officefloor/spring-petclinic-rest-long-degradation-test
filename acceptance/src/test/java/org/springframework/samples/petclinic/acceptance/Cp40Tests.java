package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** membership-points: points = +2 email, +1 namesake 0, +2 household of 3+, +3 tenure over
 * 365 days; mapped to level 1 (0-1) / 2 (2-3) / 3 (4-5) / 4 (6+). A fresh owner with an email and
 * no namesake scores 3 points (2 + 1), a single-member household, zero tenure -> level 2. */
@Tag("cp40")
class Cp40Tests extends AcceptanceBase {

	@Test
	void coreReturnsPointsAndLevel() throws Exception {
		ObjectNode o = withPostcode(ownerNode());
		o.put("email", uniqueEmail());
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.membershipPoints").value(3))
				.andExpect(jsonPath("$.membershipLevel").value(2));
	}
}
