package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** cp40 membership-points: Replace the level rules with a points system: start at 0; add 2 when an email is present;... */
@Tag("cp40")
class Cp40Tests extends AcceptanceBase {

	@Test
	void coreReturnsPointsAndLevel() throws Exception {
		ObjectNode o = withPostcode(ownerNode());
		o.put("email", uniqueEmail());
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.membershipPoints").exists())
				.andExpect(jsonPath("$.membershipLevel").exists()); // TODO: assert mapping
	}
}
