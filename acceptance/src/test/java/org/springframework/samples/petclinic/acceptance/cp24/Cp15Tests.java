package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** cp15 membership-tier, UPDATED by cp24: the string tier is gone; a numeric membershipLevel replaces
 *  it. A unique owner with an email scores level 3 (1 + email + namesake 0). */
@Tag("cp15")
class Cp15Tests extends AcceptanceBase {

	@Test
	void coreNumericLevelReplacesTier() throws Exception {
		ObjectNode o = ownerNode();
		o.put("email", uniqueEmail());
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.membershipLevel").value(3))
				.andExpect(jsonPath("$.membershipTier").doesNotExist());
	}
}
