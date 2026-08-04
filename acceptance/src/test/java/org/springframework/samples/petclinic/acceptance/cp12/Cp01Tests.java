package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** cp01 required-fields: UPDATED by cp12 (address-normalize) — an address blank after normalization is rejected. */
@Tag("cp01")
class Cp01Tests extends AcceptanceBase {

	@Test
	void coreRejectsWhitespaceOnlyAddress() throws Exception {
		ObjectNode o = ownerNode();
		o.put("address", "   ");
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void errorStillRejectsMissingCity() throws Exception {
		ObjectNode o = ownerNode();
		o.remove("city");
		createOwner(o).andExpect(status().isBadRequest());
	}
}
