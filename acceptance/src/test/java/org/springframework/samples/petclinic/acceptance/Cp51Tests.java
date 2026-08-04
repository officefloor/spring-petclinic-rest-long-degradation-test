package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp51 level-ceiling: A new owner's membershipLevel cannot exceed one above the current maximum membershipLevel... */
@Tag("cp51")
class Cp51Tests extends AcceptanceBase {

	@Test
	void coreCapsLevelByHousehold() throws Exception {
		// TODO: existing high-level household member caps a new member
		int id = createOwnerOk(structuredOwner());
		getOwner(id).andExpect(jsonPath("$.membershipLevel").exists());
	}
}
