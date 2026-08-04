package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** cp46 exclude-deleted: The duplicate and identity checks must ignore owners flagged 'deleted' true; a normally-bl... */
@Tag("cp46")
class Cp46Tests extends AcceptanceBase {

	@Test
	void coreIgnoresDeletedOnDuplicate() throws Exception {
		// TODO: create, soft-delete, then a matching create should succeed
		int id = createOwnerOk(structuredOwner());
		getOwner(id).andExpect(status().is2xxSuccessful());
	}
}
