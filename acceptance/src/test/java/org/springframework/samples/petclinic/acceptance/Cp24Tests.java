package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** membership-levels: Replace the string membership tier with a numeric 'membershipLevel' from 1 to 3 on creatio... */
@Tag("cp24")
class Cp24Tests extends AcceptanceBase {

	@Test
	void coreNumericLevel() throws Exception {
		ObjectNode o = ownerNode();
		o.put("firstName", "Uniq"); o.put("lastName", "levelsolo");
		o.put("email", uniqueEmail());
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.membershipLevel").value(3)); // 1 +email +namesake0, capped 3
	}
}
