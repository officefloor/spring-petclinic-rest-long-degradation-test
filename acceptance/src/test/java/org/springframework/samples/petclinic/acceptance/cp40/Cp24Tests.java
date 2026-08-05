package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** cp24 membership-levels, UPDATED by cp40: membershipLevel now comes from points. A new owner with
 *  an email scores 3 points (2 email + 1 namesake 0), which maps to level 2. */
@Tag("cp24")
class Cp24Tests extends AcceptanceBase {

	@Test
	void corePointsDriveLevel() throws Exception {
		ObjectNode o = withPostcode(ownerNode());
		o.put("email", uniqueEmail());
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.membershipPoints").value(3))
				.andExpect(jsonPath("$.membershipLevel").value(2));
	}
}
