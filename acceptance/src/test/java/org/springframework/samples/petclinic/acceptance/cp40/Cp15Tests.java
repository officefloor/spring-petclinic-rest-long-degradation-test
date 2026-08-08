package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** membership-tier: membershipLevel now comes from points, not the old cap-3
 * rule. A unique owner with an email scores 3 points (2 email + 1 namesake 0), which maps to
 * level 2 (the 2-3 point band). The string tier stays gone. */
@Tag("cp15")
class Cp15Tests extends AcceptanceBase {

	@Test
	void coreNumericLevelFromPoints() throws Exception {
		ObjectNode o = ownerNode();
		o.put("email", uniqueEmail());
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.membershipPoints").value(3))
				.andExpect(jsonPath("$.membershipLevel").value(2))
				.andExpect(jsonPath("$.membershipTier").doesNotExist());
	}
}
