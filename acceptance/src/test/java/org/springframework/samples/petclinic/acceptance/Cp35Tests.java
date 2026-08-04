package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp35 soft-match: When a new owner is not a hard duplicate but shares an existing owner's lastName and postc... */
@Tag("cp35")
class Cp35Tests extends AcceptanceBase {

	@Test
	void coreFlagsPossibleDuplicate() throws Exception {
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(jsonPath("$.possibleDuplicate").value(false)); // TODO: true on lastName+postcode near-match
	}
}
