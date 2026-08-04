package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** cp32 global-id: UPDATED by cp48 (fiscal-year) — Move date-derived values to a fiscal-year basis, where the fiscal year starts on 1 July */
@Tag("cp32")
class Cp32Tests extends AcceptanceBase {

	@Test
	void coreUpdatedBehaviour() throws Exception {
		// This rule changed. Move date-derived values to a fiscal-year basis, where the fiscal year starts on 1 July.
		// TODO: assert the UPDATED behaviour of "global-id" under the new spec.
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(status().is2xxSuccessful());
	}
}
